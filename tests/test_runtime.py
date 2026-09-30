import json
import tempfile
import unittest
from pathlib import Path

from assistant.agents import AgentManager
from assistant.approvals import ApprovalService
from assistant.config import ROOT, load_config
from assistant.context import ContextOverflow, ContextService
from assistant.models import LLMResponse, ToolCall
from assistant.providers.gateway import ProviderGateway
from assistant.runtime import Runtime
from assistant.storage import Store
from assistant.tools import ToolDefinition, ToolRegistry, ToolRuntime, object_schema, register_safe_tools
from assistant.workspace import Workspace


class QueueAdapter:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def prepare(self, request):
        return {}

    def complete(self, request, payload):
        self.requests.append(request)
        return next(self.responses)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.store = Store(self.path / 'test.db')
        self.agents = AgentManager(self.store)
        self.agents.seed(ROOT / 'config/agents')
        self.registry = ToolRegistry()
        self.workspace = Workspace(self.path / 'workspace', self.store)
        register_safe_tools(self.registry, self.workspace)
        # Future capability names are absent from the first runtime milestone.
        profile = self.agents.get('personal')
        profile.tools = ['current_time', 'read_file', 'write_note']
        self.agents.update(profile)
        self.context = ContextService(self.store, ROOT, self.registry)

    def runtime(self, responses, max_steps=10):
        self.adapter = QueueAdapter(responses)
        return Runtime(self.store, self.agents, self.context,
                       ProviderGateway(self.store, {'gemini': self.adapter}, load_config()['retry']),
                       ToolRuntime(self.store, self.registry), max_steps)

    def test_routing_and_continuity(self):
        runtime = self.runtime([LLMResponse(tool_calls=[ToolCall('escalate', {})]), LLMResponse(text='Working on X')])
        result = runtime.user_message('Remember X')
        self.assertEqual(result.text, 'Working on X')
        runs = self.store.rows('SELECT * FROM runs ORDER BY rowid')
        self.assertEqual(runs[1]['parent_run_id'], runs[0]['id'])
        self.assertEqual([r.agent_id for r in self.adapter.requests], ['tier1', 'personal'])
        self.assertEqual(len(self.adapter.requests[0].messages), 1)
        self.assertEqual([r['content'] for r in self.store.rows('SELECT content FROM messages ORDER BY id')],
                         ['Remember X', 'Working on X'])

    def test_tool_cycle_and_full_result_preservation(self):
        runtime = self.runtime([LLMResponse(tool_calls=[ToolCall('current_time', {})]), LLMResponse(text='Time shown')])
        self.assertEqual(runtime.user_message('time').text, 'Time shown')
        self.assertEqual(self.adapter.requests[1].messages[-1].role, 'tool')
        self.assertEqual(self.store.one('SELECT status FROM tool_calls')['status'], 'completed')

    def test_limit_applies_to_calls_in_batch(self):
        runtime = self.runtime([LLMResponse(tool_calls=[ToolCall('current_time', {})] * 11)])
        with self.assertLogs('assistant.runtime', level='ERROR'):
            with self.assertRaisesRegex(ValueError, 'Tool-step limit'):
                runtime.user_message('loop')
        self.assertEqual(len(self.store.rows('SELECT * FROM tool_calls')), 10)
        self.assertEqual(self.store.one('SELECT status FROM runs')['status'], 'failed')

    def test_approval_survives_restart_and_resumes_once(self):
        runtime = self.runtime([LLMResponse(tool_calls=[ToolCall('escalate', {})]),
                                LLMResponse(tool_calls=[ToolCall('write_note', {'path': 'note.md', 'content': 'hello'})])])
        result = runtime.user_message('write a note')
        self.assertEqual(result.status, 'waiting')
        self.assertFalse((self.workspace.root / 'note.md').exists())
        with self.assertRaisesRegex(ValueError, 'pending approval'):
            runtime.user_message('another input')
        restarted = self.runtime([LLMResponse(text='Created')])
        restarted.recover_interrupted()
        approvals = ApprovalService(Store(self.path / 'test.db'))
        self.assertEqual(len(approvals.pending()), 1)
        run_id = approvals.resolve(approvals.pending()[0]['id'], True)
        self.assertEqual(restarted.resume(run_id).text, 'Created')
        self.assertEqual((self.workspace.root / 'note.md').read_text(), 'hello')
        with self.assertRaises(ValueError):
            restarted.resume(run_id)
        self.assertEqual(len(self.store.rows("SELECT * FROM tool_calls WHERE tool_name='write_note'")), 1)

    def test_denial_and_invalid_tool_do_not_execute(self):
        runtime = self.runtime([LLMResponse(tool_calls=[ToolCall('escalate', {})]),
                                LLMResponse(tool_calls=[ToolCall('write_note', {'path': 'denied.md', 'content': 'no'})])])
        runtime.user_message('note')
        approval = ApprovalService(self.store)
        run_id = approval.resolve(approval.pending()[0]['id'], False)
        resumed = self.runtime([LLMResponse(text='Denied')])
        self.assertEqual(resumed.resume(run_id).text, 'Denied')
        self.assertFalse((self.workspace.root / 'denied.md').exists())
        runtime = self.runtime([LLMResponse(tool_calls=[ToolCall('write_note', {'path': '../escape.md', 'content': 'x'})]),
                                LLMResponse(text='Not allowed')])
        runtime.user_message('router cannot write')
        self.assertEqual(self.store.rows('SELECT status FROM tool_calls ORDER BY id')[-1]['status'], 'failed')

    def test_workspace_bounds_and_context_limits(self):
        with self.assertRaises(ValueError):
            self.workspace.read('../outside')
        profile = self.agents.get('personal')
        session = self.store.session()
        self.store.message(session, 'user', 'magerram', 'old' * 10000)
        current = self.store.message(session, 'user', 'magerram', 'current input')
        profile.context['max_characters'] = 4000
        built = self.context.build(profile, session, current)
        self.assertEqual(built.messages[-1].text, 'current input')
        self.assertLess(len(json.dumps(__import__('dataclasses').asdict(built), ensure_ascii=False)), 4001)
        profile.context['max_characters'] = 10
        with self.assertRaises(ContextOverflow):
            self.context.build(profile, session, current)
