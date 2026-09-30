import json
import tempfile
import unittest
from pathlib import Path

from assistant.agents import AgentManager
from assistant.config import ROOT, load_config
from assistant.storage import Store


class StorageTests(unittest.TestCase):
    def test_restart_and_full_schema(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / 'test.db'
            store = Store(path)
            agents = AgentManager(store)
            agents.seed(ROOT / 'config/agents')
            session = store.session()
            message = store.message(session, 'user', 'magerram', 'working on X')
            parent = store.run(session, 'personal')
            internal = store.session('agent', 'personal', 'expert')
            child = store.run(internal, 'expert', parent)
            store.finish(child)
            restarted = Store(path)
            self.assertEqual(restarted.session(), session)
            self.assertEqual(restarted.one('SELECT content FROM messages WHERE id=?', (message,))['content'], 'working on X')
            self.assertEqual(restarted.one('SELECT parent_run_id FROM runs WHERE id=?', (child,))['parent_run_id'], parent)
            self.assertEqual(restarted.session('agent', 'personal', 'expert', internal), internal)
            self.assertNotEqual(restarted.session('agent', 'personal', 'expert'), internal)
            with self.assertRaises(ValueError):
                restarted.session('agent', 'tier1', 'expert', internal)
            tables = {row['name'] for row in restarted.rows("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({'agents', 'sessions', 'messages', 'runs', 'api_calls', 'tool_calls',
                             'approvals', 'scheduled_jobs', 'memory_items', 'files'} <= tables)
            self.assertNotIn('tasks', tables)
            self.assertNotIn('agent_jobs', tables)

    def test_profile_seed_does_not_override_database(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            manager = AgentManager(Store(Path(directory) / 'test.db'))
            manager.seed(ROOT / 'config/agents')
            profile = manager.get('personal')
            profile.model = 'custom-model'
            manager.update(profile)
            manager.seed(ROOT / 'config/agents')
            self.assertEqual(manager.get('personal').model, 'custom-model')

    def test_config_rejects_excessive_loop(self):
        config = load_config()
        config['runtime']['max_tool_steps'] = 11
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / 'config.json'
            path.write_text(json.dumps(config), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_config(path)
