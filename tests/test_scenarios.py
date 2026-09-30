import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock

from assistant.app import Application
from assistant.config import ROOT, load_config
from assistant.models import LLMResponse, ToolCall
from assistant.storage import Store


class FunctionAdapter:
    def __init__(self, function):
        self.function = function
        self.requests = []
        self.guard = Lock()

    def prepare(self, request):
        return {}

    def complete(self, request, payload):
        with self.guard:
            self.requests.append(request)
        return self.function(request)


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.config = load_config()
        self.config['paths']['database'] = str(Path(self.temp.name) / 'test.db')
        self.config['paths']['workspace'] = str(Path(self.temp.name) / 'workspace')
        self.apps = []
        self.addCleanup(self.close_apps)

    def close_apps(self):
        for app in self.apps:
            app.close()

    def app(self, function):
        self.adapter = FunctionAdapter(function)
        app = Application(config=self.config, adapters={'gemini': self.adapter})
        self.apps.append(app)
        return app

    def test_personal_memory_after_response_raw_history_survives(self):
        def provider(request):
            if request.settings.get('response_json'):
                snapshot = json.loads(request.messages[0].text)
                self.assertEqual(snapshot['messages'][-1]['content'], 'I will remember X')
                return LLMResponse(text=json.dumps({'retain_message_ids': [], 'active': 'Magerram works on X',
                    'short': 'Today: started X', 'expert_summary': ''}))
            if request.agent_id == 'tier1':
                return LLMResponse(tool_calls=[ToolCall('escalate', {})])
            return LLMResponse(text='I will remember X')
        app = self.app(provider)
        profile = app.agents.get('personal')
        profile.memory.update(threshold_characters=1, recent_messages=1)
        app.agents.update(profile)
        result = app.runtime.user_message('I am working on X')
        self.assertEqual(len(self.adapter.requests), 2)
        self.assertEqual(app.store.rows('SELECT * FROM memory_items'), [])
        # Caller has now displayed/received the response, then invokes maintenance.
        app.memory.enqueue('personal', result.session_id).result(timeout=10)
        self.assertEqual(len(app.store.rows('SELECT * FROM messages')), 2)
        self.assertEqual(len(app.context.transcript(result.session_id)), 1)
        current = app.store.message(result.session_id, 'user', 'magerram', 'What was I working on?')
        built = app.context.build(app.agents.get('personal'), result.session_id, current)
        self.assertIn('Magerram works on X', built.system)
        self.assertTrue(list(app.workspace.root.glob('activity/*.md')))
        restarted = Store(app.store.path)
        self.assertEqual(restarted.session(), result.session_id)
        self.assertEqual(len(restarted.rows('SELECT * FROM messages')), 3)
        self.assertEqual(restarted.one("SELECT content FROM memory_items WHERE layer='active'")['content'], 'Magerram works on X')

    def test_invalid_memory_does_not_compact_or_replace_state(self):
        app = self.app(lambda request: LLMResponse(text=json.dumps({'retain_message_ids': [999999],
            'active': 'invented', 'short': '', 'expert_summary': ''})))
        session = app.store.session()
        app.store.message(session, 'user', 'magerram', 'keep this')
        app.store.execute("INSERT INTO memory_items (layer,content) VALUES ('active','existing')")
        with self.assertRaisesRegex(ValueError, 'outside its input'):
            app.memory.maintain('personal', session)
        self.assertIsNone(app.store.one('SELECT * FROM context_state'))
        self.assertEqual(app.store.one('SELECT content FROM memory_items')['content'], 'existing')
        self.assertEqual(len(app.store.rows('SELECT * FROM messages')), 1)

    def test_expert_is_background_and_continues_same_session(self):
        started, release = Event(), Event()
        def provider(request):
            if request.agent_id == 'expert':
                started.set()
                if not release.wait(10):
                    raise ValueError('Test expert did not get released')
                return LLMResponse(text='Expert result')
            return LLMResponse(text='Still available')
        app = self.app(provider)
        self.addCleanup(release.set)
        session = app.store.session()
        parent = app.store.run(session, 'personal')
        execution = {'profile': app.agents.get('personal'), 'run_id': parent, 'session_id': session}
        delegated = app.runtime.delegate(execution, 'expert', 'first task')
        self.assertTrue(started.wait(5))
        self.assertEqual(app.runtime.user_message('hello').text, 'Still available')
        child = app.store.one('SELECT * FROM runs WHERE id=?', (delegated['run_id'],))
        self.assertEqual(child['parent_run_id'], parent)
        self.assertEqual(child['status'], 'running')
        release.set()
        app.background.close()
        self.assertEqual(app.store.one('SELECT status FROM runs WHERE id=?', (child['id'],))['status'], 'completed')
        self.assertIn('Expert result', app.store.rows('SELECT content FROM messages WHERE session_id=? ORDER BY id', (session,))[-1]['content'])
        # Use a second application after the first executor has been shut down.
        app.close()
        self.apps.remove(app)
        app = self.app(provider)
        continued = app.runtime.delegate(execution, 'expert', 'follow up', delegated['session_id'])
        app.background.close()
        self.assertEqual(continued['session_id'], delegated['session_id'])
        expert_requests = [request for request in self.adapter.requests if request.agent_id == 'expert']
        self.assertIn('Expert result', [message.text for message in expert_requests[-1].messages])

    def test_expert_light_compaction_uses_session_summary(self):
        def provider(request):
            return LLMResponse(text=json.dumps({'retain_message_ids': [], 'active': '', 'short': '',
                                               'expert_summary': 'Research X is half complete'}))
        app = self.app(provider)
        session = app.store.session('agent', 'personal', 'expert')
        for i in range(8):
            app.store.message(session, 'agent', 'personal' if i % 2 == 0 else 'expert', f'message {i}')
        app.memory.maintain('expert', session)
        self.assertEqual(len(app.store.rows('SELECT * FROM messages')), 8)
        self.assertEqual(len(app.context.transcript(session)), 6)
        current = app.store.message(session, 'agent', 'personal', 'continue')
        built = app.context.build(app.agents.get('expert'), session, current)
        self.assertIn('Research X is half complete', built.system)
        self.assertEqual(app.store.rows('SELECT * FROM memory_items'), [])

    def test_one_time_wakeup_runs_normal_runtime_and_is_not_duplicated(self):
        app = self.app(lambda request: LLMResponse(text='Wakeup done'))
        session = app.store.session()
        app.scheduler.clock = lambda: datetime(2026, 1, 1, 7, 59, tzinfo=timezone.utc)
        scheduled = app.scheduler.schedule('personal', session, 'reminder', '2026-01-01T12:00:00+04:00')
        jobs = app.scheduler.tick('2026-01-01T08:00:01Z')
        self.assertEqual(len(jobs), 1)
        jobs[0].result(timeout=10)
        self.assertEqual(app.scheduler.tick('2026-01-01T08:01:00Z'), [])
        self.assertEqual(app.store.one('SELECT status FROM scheduled_jobs WHERE id=?', (scheduled['job_id'],))['status'], 'completed')
        self.assertEqual(app.store.one('SELECT status FROM api_calls')['status'], 'completed')
        self.assertEqual(app.store.one('SELECT status FROM runs')['status'], 'completed')
        self.assertEqual(app.notifications.get_nowait().text, 'Wakeup done')
        with self.assertRaises(ValueError):
            app.scheduler.schedule('personal', session, 'bad time', '2026-01-01T12:00:00')
