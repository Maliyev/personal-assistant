import json
from dataclasses import asdict
from datetime import datetime, timezone

from assistant.background import BackgroundBusy
from assistant.models import ScheduledWakeup


def utc_time(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Wakeup must include a timezone offset')
    return parsed.astimezone(timezone.utc).isoformat(timespec='microseconds')


class Scheduler:
    def __init__(self, store, runtime, background, on_response=None, clock=None):
        self.store, self.runtime, self.background = store, runtime, background
        self.on_response = on_response
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def schedule(self, agent_id, session_id, payload, at):
        self.runtime.agents.get(agent_id)
        session = self.store.one('SELECT * FROM sessions WHERE id=?', (session_id,))
        if not session or session['participant_b_id'] != agent_id:
            raise ValueError('Scheduled target must match the session target')
        instant = utc_time(at)
        now = self.clock().astimezone(timezone.utc)
        if datetime.fromisoformat(instant) <= now:
            raise ValueError(f'Wakeup time must be in the future. Current UTC time: {now.isoformat()}')
        job_id = self.store.execute('''INSERT INTO scheduled_jobs
            (target_agent_id,session_id,payload,schedule,next_run_at) VALUES (?,?,?,'once',?)''',
            (agent_id, session_id, payload, instant))
        return {'job_id': job_id, 'next_run_at': instant}

    def tick(self, now=None):
        instant = utc_time(now) if now else self.clock().astimezone(timezone.utc).isoformat(timespec='microseconds')
        jobs = self.store.rows("SELECT * FROM scheduled_jobs WHERE status='pending' AND next_run_at<=? ORDER BY id", (instant,))
        submitted = []
        for job in jobs:
            with self.store.connect() as connection:
                changed = connection.execute("UPDATE scheduled_jobs SET status='running' WHERE id=? AND status='pending'", (job['id'],)).rowcount
            if not changed:
                continue
            try:
                submitted.append(self.background.submit(lambda job=job: self._execute(job)))
            except BackgroundBusy:
                self.store.execute("UPDATE scheduled_jobs SET status='pending' WHERE id=?", (job['id'],))
                break
        return submitted

    def _execute(self, job):
        session_id = job['session_id']
        try:
            with self.runtime.session_lock(session_id):
                if self.store.one("SELECT id FROM runs WHERE session_id=? AND status='waiting'", (session_id,)):
                    self.store.execute("UPDATE scheduled_jobs SET status='pending' WHERE id=?", (job['id'],))
                    return
                event = ScheduledWakeup(job['id'], job['next_run_at'],
                    self.clock().astimezone(timezone.utc).isoformat(timespec='microseconds'), job['payload'])
                current_id = self.store.message(session_id, 'system', 'scheduler',
                    json.dumps(asdict(event), ensure_ascii=False))
                result = self.runtime.activate(job['target_agent_id'], session_id, current_id)
                self.store.execute('UPDATE scheduled_jobs SET status=? WHERE id=?', (result.status, job['id']))
            if self.on_response:
                self.on_response(result)
        except Exception:
            self.store.execute("UPDATE scheduled_jobs SET status='failed' WHERE id=?", (job['id'],))
            raise

    def recover_interrupted(self):
        self.store.execute("UPDATE scheduled_jobs SET status='failed' WHERE status='running'")
