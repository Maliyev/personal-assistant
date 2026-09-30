import logging
import time
from queue import Queue
from threading import Event, Thread

from assistant.agents import AgentManager
from assistant.approvals import ApprovalService
from assistant.background import BackgroundWork
from assistant.config import ROOT, load_config, load_env
from assistant.context import ContextService
from assistant.memory import MemoryManager
from assistant.providers.gateway import ProviderGateway
from assistant.providers.gemini import GeminiAdapter
from assistant.runtime import Runtime
from assistant.scheduler import Scheduler
from assistant.storage import Store
from assistant.tools import ToolDefinition, ToolRegistry, ToolRuntime, object_schema, register_safe_tools
from assistant.workspace import Workspace

logger = logging.getLogger(__name__)


class Application:
    def __init__(self, root=ROOT, config=None, adapters=None):
        self.root = root
        self.config = config or load_config(root / 'config/config.json')
        load_env(root / '.env')
        self.store = Store(root / self.config['paths']['database'])
        self.agents = AgentManager(self.store)
        self.agents.seed(root / self.config['paths']['agent_seeds'])
        self.registry = ToolRegistry()
        self.workspace = Workspace(root / self.config['paths']['workspace'], self.store,
                                   self.config['workspace']['max_read_bytes'])
        register_safe_tools(self.registry, self.workspace)
        self.context = ContextService(self.store, root, self.registry)
        adapters = adapters if adapters is not None else {
            'gemini': GeminiAdapter(self.config['providers']['gemini'], self.config['runtime']['request_timeout_seconds'])}
        self.gateway = ProviderGateway(self.store, adapters, self.config['retry'])
        self.tools = ToolRuntime(self.store, self.registry)
        self.runtime = Runtime(self.store, self.agents, self.context, self.gateway, self.tools,
                               self.config['runtime']['max_tool_steps'])
        self.background = BackgroundWork(self.config['runtime']['background_workers'],
                                         self.config['runtime']['background_queue_limit'])
        self.runtime.background = self.background
        self.notifications = Queue()
        self.memory = MemoryManager(self.store, self.agents, self.context, self.gateway,
                                    self.background, self.runtime, self.workspace)
        self.runtime.after_response = self.after_response
        self.scheduler = Scheduler(self.store, self.runtime, self.background, self._scheduled_response)
        self.approvals = ApprovalService(self.store)
        self._register_communication()
        self.runtime.recover_interrupted()
        self.scheduler.recover_interrupted()
        self.stop = Event()
        self.thread = None
        self.closing = False

    def _register_communication(self):
        text = {'type': 'string', 'minLength': 1}
        self.registry.register(ToolDefinition('send_agent', 'Start or continue background expert work.',
            object_schema({'target_agent': text, 'message': text, 'session_id': text}, ['target_agent', 'message']),
            lambda execution, **arguments: self.runtime.delegate(execution, **arguments), return_mode='async_result'))
        self.registry.register(ToolDefinition('run_status', 'Inspect the persisted status and latest session result of a delegated run.',
            object_schema({'run_id': text}, ['run_id']), self.runtime.run_status))
        self.registry.register(ToolDefinition('schedule_wakeup', 'Schedule a one-time future activation of this agent in this session; at must be ISO 8601 with a timezone offset and strictly later than the current time. Past or present times return an error.',
            object_schema({'message': text, 'at': text}, ['message', 'at']),
            lambda execution, message, at: self.scheduler.schedule(execution['profile'].id,
                execution['session_id'], message, at)))

    def after_response(self, result):
        if result.status == 'completed' and not self.closing:
            row = self.store.one('SELECT agent_id FROM runs WHERE id=?', (result.run_id,))
            self.memory.enqueue(row['agent_id'], result.session_id)

    def _scheduled_response(self, result):
        self.notifications.put(result)
        self.after_response(result)

    def start_services(self):
        if self.thread:
            return
        def loop():
            last_memory = time.monotonic()
            while not self.stop.wait(self.config['scheduler']['tick_seconds']):
                try:
                    self.scheduler.tick()
                    if time.monotonic() - last_memory >= self.config['memory']['periodic_seconds']:
                        self.memory.periodic()
                        last_memory = time.monotonic()
                except Exception:
                    logger.exception('Background service tick failed')
        self.thread = Thread(target=loop, name='scheduler', daemon=True)
        self.thread.start()

    def close(self):
        self.closing = True
        self.stop.set()
        if self.thread:
            self.thread.join()
        self.background.close()
