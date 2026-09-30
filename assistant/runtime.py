import json
import logging
from dataclasses import asdict, dataclass
from threading import Lock

from assistant.models import Message, ToolCall, restore_message

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    text: str
    run_id: str
    session_id: str
    status: str = 'completed'
    route_to: str | None = None


class Runtime:
    def __init__(self, store, agents, context, gateway, tools, max_tool_steps, tier1_enabled=True):
        self.store, self.agents, self.context = store, agents, context
        self.gateway, self.tools = gateway, tools
        if type(max_tool_steps) is not int or not 1 <= max_tool_steps <= 10:
            raise ValueError('V0 permits 1 to 10 tool steps')
        self.max_tool_steps = max_tool_steps
        self.tier1_enabled = tier1_enabled
        self._locks = {}
        self._locks_guard = Lock()

    def session_lock(self, session_id):
        with self._locks_guard:
            return self._locks.setdefault(session_id, Lock())

    def user_message(self, text):
        session_id = self.store.session()
        with self.session_lock(session_id):
            waiting = self.store.one("SELECT id FROM runs WHERE session_id=? AND status='waiting'", (session_id,))
            if waiting:
                raise ValueError(f"Resolve pending approval for run {waiting['id']} before continuing this session")
            current_id = self.store.message(session_id, 'user', 'magerram', text)
            if not self.tier1_enabled:
                return self.activate('personal', session_id, current_id)
            routed = self.activate('tier1', session_id, current_id)
            if routed.route_to:
                return self.activate(routed.route_to, session_id, current_id, parent_run_id=routed.run_id)
            return routed

    def activate(self, agent_id, session_id, current_id, parent_run_id=None, run_id=None):
        run_id = run_id or self.store.run(session_id, agent_id, parent_run_id)
        try:
            profile = self.agents.get(agent_id)
            return self._loop(profile, session_id, run_id, {
                'current_id': current_id, 'messages': [], 'steps': 0, 'calls': [],
                'index': 0, 'tool_ids': [], 'api_call_id': None, 'last_text': ''})
        except Exception as error:
            self.store.finish(run_id, 'failed', str(error))
            logger.exception('Run failed agent=%s run=%s', agent_id, run_id)
            raise

    def resume(self, run_id):
        row = self.store.one('SELECT * FROM runs WHERE id=?', (run_id,))
        if row is None:
            raise ValueError('Unknown run')
        with self.session_lock(row['session_id']):
            row = self.store.one('SELECT * FROM runs WHERE id=?', (run_id,))
            if row['status'] != 'waiting' or not row['state_json']:
                raise ValueError('Run is not waiting for approval')
            state = json.loads(row['state_json'])
            try:
                return self._loop(self.agents.get(row['agent_id']), row['session_id'], run_id, state)
            except Exception as error:
                self.store.finish(run_id, 'failed', str(error))
                raise

    def _loop(self, profile, session_id, run_id, state):
        messages = [restore_message(message) for message in state['messages']]
        while True:
            if not state['calls']:
                request = self.context.build(profile, session_id, state['current_id'], messages)
                response = self.gateway.complete(request, run_id, session_id)
                if response.finish_reason == 'length':
                    raise ValueError('Model output reached its token limit; incomplete response preserved in api_calls')
                if not response.tool_calls:
                    return self._complete(profile, session_id, run_id, response.text)
                messages.append(response.continuation or Message('assistant', response.text, response.tool_calls))
                state.update(calls=[asdict(call) for call in response.tool_calls], index=0,
                             tool_ids=[None] * len(response.tool_calls), api_call_id=response.api_call_id,
                             last_text=response.text, terminal_results=[], requires_resume=False)
            while state['index'] < len(state['calls']):
                index = state['index']
                call = ToolCall(**state['calls'][index])
                persisted_id = state['tool_ids'][index]
                if persisted_id is None:
                    if state['steps'] >= self.max_tool_steps:
                        raise ValueError(f'Tool-step limit reached ({self.max_tool_steps})')
                    state['steps'] += 1
                tool_id, status, result, mode = self.tools.call(
                    call, profile, run_id, session_id, state['api_call_id'],
                    {'runtime': self, 'profile': profile, 'run_id': run_id, 'session_id': session_id}, persisted_id)
                state['tool_ids'][index] = tool_id
                if status == 'waiting':
                    state['messages'] = [asdict(message) for message in messages]
                    self.store.finish(run_id, 'waiting', state=state)
                    return RunResult('Tool requires approval. Use /approvals, then /approve ID or /deny ID.',
                                     run_id, session_id, 'waiting')
                messages.append(self.context.tool_result(profile, call.name, result, call.id))
                state['index'] += 1
                if isinstance(result, dict) and result.get('route_to'):
                    if profile.tier != 1 or result['route_to'] != 'personal':
                        raise ValueError('Invalid routing target')
                    if len(state['calls']) != 1:
                        raise ValueError('Escalation must be the only tool call in a response')
                    self.store.finish(run_id)
                    return RunResult('', run_id, session_id, route_to='personal')
                state['requires_resume'] |= mode == 'resume_agent' or status in ('failed', 'denied')
                state['terminal_results'].append(result)
            state['calls'] = []
            if not state['requires_resume']:
                summary = json.dumps(state['terminal_results'], ensure_ascii=False)
                text = (state['last_text'] + '\n' if state['last_text'] else '') + summary
                return self._complete(profile, session_id, run_id, text)

    def _complete(self, profile, session_id, run_id, text):
        self.store.message(session_id, 'agent', profile.id, text)
        self.store.finish(run_id)
        return RunResult(text, run_id, session_id)

    def delegate(self, execution, target_agent, message, session_id=None):
        target = self.agents.get(target_agent)
        if target.tier != 3:
            raise ValueError('Delegation target must be an expert')
        caller = execution['profile'].id
        internal = self.store.session('agent', caller, target_agent, session_id)
        child = self.store.run(internal, target_agent, execution['run_id'])

        def work():
            try:
                with self.session_lock(internal):
                    if self.store.one("SELECT id FROM runs WHERE session_id=? AND status='waiting'", (internal,)):
                        raise ValueError('Expert session is waiting for approval')
                    current = self.store.message(internal, 'agent', caller, message)
                    result = self.activate(target_agent, internal, current, run_id=child)
                with self.session_lock(execution['session_id']):
                    self.store.message(execution['session_id'], 'agent', target_agent,
                        f"[Expert run {child}; session {internal}; {result.status}]\n{result.text}")
                if hasattr(self, 'after_response'):
                    self.after_response(result)
            except Exception as error:
                self.store.finish(child, 'failed', str(error))
                self.store.message(execution['session_id'], 'agent', target_agent,
                                   f'[Expert run {child} failed]\n{error}')
                logger.exception('Expert failed run=%s', child)
        try:
            self.background.submit(work)
        except Exception as error:
            self.store.finish(child, 'failed', str(error))
            raise
        return {'run_id': child, 'session_id': internal, 'status': 'submitted'}

    def run_status(self, execution, run_id):
        row = self.store.one('SELECT * FROM runs WHERE id=?', (run_id,))
        if not row:
            raise ValueError('Unknown run')
        session = self.store.one('SELECT * FROM sessions WHERE id=?', (row['session_id'],))
        caller = execution['profile'].id
        if row['session_id'] != execution['session_id'] and session['participant_a_id'] != caller:
            raise PermissionError('Run is not accessible to this agent')
        messages = self.store.rows("SELECT content FROM messages WHERE session_id=? AND sender_id=? ORDER BY id DESC LIMIT 1",
                                   (row['session_id'], row['agent_id']))
        return {'run_id': run_id, 'session_id': row['session_id'], 'status': row['status'],
                'error': row['error'], 'latest_session_result': messages[0]['content'] if messages else None}

    def recover_interrupted(self):
        # Never replay uncertain external side effects automatically.
        self.store.execute("""UPDATE runs SET status='failed',error='Interrupted by process restart',
            finished_at=CURRENT_TIMESTAMP WHERE status='running'""")
        self.store.execute("""UPDATE tool_calls SET status='failed',
            result='{"error":"Interrupted; effect may have occurred. Not replayed."}',
            finished_at=CURRENT_TIMESTAMP WHERE status IN ('requested','executing')""")
