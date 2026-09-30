import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from assistant.app import Application
from assistant.config import ROOT, load_config
from assistant.models import LLMResponse
from test_scenarios import FunctionAdapter


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(temporary.cleanup)
        config = load_config()
        config['paths']['database'] = str(Path(temporary.name) / 'test.db')
        config['paths']['workspace'] = str(Path(temporary.name) / 'workspace')
        self.adapter = FunctionAdapter(lambda request: LLMResponse(text='привет, все работает'))
        self.app = Application(config=config, adapters={'gemini': self.adapter})
        self.addCleanup(self.app.close)
        self.now = datetime(2026, 9, 30, 14, 0, tzinfo=timezone.utc)
        self.app.scheduler.clock = lambda: self.now
        self.session = self.app.store.session()

    def test_past_and_present_times_fail_without_creating_a_job(self):
        for at in ('2026-09-30T17:59:59+04:00', '2026-09-30T18:00:00+04:00'):
            with self.assertRaisesRegex(ValueError, 'must be in the future'):
                self.app.scheduler.schedule('personal', self.session, 'hello', at)
        self.assertEqual(self.app.store.rows('SELECT * FROM scheduled_jobs'), [])

    def test_overdue_future_job_produces_typed_wakeup_context_once(self):
        at = (self.now + timedelta(minutes=2)).isoformat()
        scheduled = self.app.scheduler.schedule('personal', self.session, 'привет, все работает', at)
        self.now += timedelta(minutes=5)
        futures = self.app.scheduler.tick()
        self.assertEqual(len(futures), 1)
        futures[0].result(timeout=10)
        request = self.adapter.requests[0]
        message = request.messages[-1]
        self.assertEqual(message.role, 'event')
        self.assertEqual(message.event_type, 'scheduled_wakeup')
        self.assertIn('not a new user request', request.system)
        self.assertIn('Execute the saved payload NOW', request.system)
        event = json.loads(message.text.split('\n', 1)[1])
        self.assertEqual(event['event_type'], 'scheduled_wakeup')
        self.assertEqual(event['job_id'], scheduled['job_id'])
        self.assertEqual(event['payload'], 'привет, все работает')
        self.assertEqual(self.app.notifications.get_nowait().text, 'привет, все работает')
        self.assertEqual(self.app.scheduler.tick(), [])
        self.assertEqual(len(self.app.store.rows('SELECT * FROM scheduled_jobs')), 1)
        # A later real user input stays a user message; the old event stays typed.
        current = self.app.store.message(self.session, 'user', 'magerram', 'continue')
        context = self.app.context.build(self.app.agents.get('personal'), self.session, current)
        self.assertEqual(context.messages[-1].role, 'user')
        self.assertIsNone(context.messages[-1].event_type)
        self.assertEqual(context.messages[0].event_type, 'scheduled_wakeup')
