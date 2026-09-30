import json
from dataclasses import dataclass
from datetime import datetime, timezone

from assistant.models import ToolSchema


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: dict
    handler: object
    approval_policy: str = 'auto'
    return_mode: str = 'resume_agent'


def validate(schema, value, path='arguments'):
    """Supported schema subset for V0 tools, not a general JSON Schema engine."""
    kinds = {'object': dict, 'string': str, 'integer': int, 'boolean': bool, 'array': list}
    expected = schema.get('type')
    if expected not in kinds or type(value) is not kinds[expected]:
        raise ValueError(f'{path} must be {expected}')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError(f'{path} is not an allowed value')
    if expected == 'string':
        if len(value) < schema.get('minLength', 0) or len(value) > schema.get('maxLength', float('inf')):
            raise ValueError(f'{path} has invalid length')
    if expected == 'integer' and value < schema.get('minimum', float('-inf')):
        raise ValueError(f'{path} is below minimum')
    if expected == 'object':
        properties = schema.get('properties', {})
        if any(key not in value for key in schema.get('required', [])):
            raise ValueError(f'{path} is missing required arguments')
        for key, item in value.items():
            if key not in properties:
                if schema.get('additionalProperties', True) is False:
                    raise ValueError(f'{path}.{key} is unexpected')
            else:
                validate(properties[key], item, f'{path}.{key}')
    if expected == 'array':
        for index, item in enumerate(value):
            validate(schema['items'], item, f'{path}[{index}]')


class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def register(self, tool):
        if tool.name in self.tools:
            raise ValueError(f'Duplicate tool: {tool.name}')
        if tool.approval_policy not in ('auto', 'required', 'deny'):
            raise ValueError('Unknown approval policy')
        if tool.return_mode not in ('resume_agent', 'fire_and_forget', 'async_result'):
            raise ValueError('Unknown tool return mode')
        self.tools[tool.name] = tool

    def get(self, name):
        if name not in self.tools:
            raise ValueError(f'Unknown tool: {name}')
        return self.tools[name]

    def schemas(self, names):
        return [ToolSchema(tool.name, tool.description, tool.input_schema)
                for tool in (self.get(name) for name in names) if tool.approval_policy != 'deny']


class ToolRuntime:
    def __init__(self, store, registry):
        self.store = store
        self.registry = registry

    def call(self, call, profile, run_id, session_id, api_call_id, execution, persisted_id=None):
        tool_id = persisted_id or self.store.execute('''INSERT INTO tool_calls
            (run_id,session_id,agent_id,api_call_id,tool_name,arguments_json,status)
            VALUES (?,?,?,?,?,?,'requested')''',
            (run_id, session_id, profile.id, api_call_id, call.name, json.dumps(call.arguments)))
        row = self.store.one('SELECT * FROM tool_calls WHERE id=?', (tool_id,))
        try:
            tool = self.registry.get(call.name)
            if call.name not in profile.tools or tool.approval_policy == 'deny':
                raise PermissionError('Tool not allowed for this agent')
            validate(tool.input_schema, call.arguments)
            if row['status'] in ('completed', 'failed', 'denied'):
                return tool_id, row['status'], json.loads(row['result']), tool.return_mode
            if tool.approval_policy == 'required':
                approval = self.store.one('SELECT * FROM approvals WHERE tool_call_id=?', (tool_id,))
                if approval is None:
                    with self.store.connect() as connection:
                        connection.execute("INSERT INTO approvals (tool_call_id) VALUES (?)", (tool_id,))
                        connection.execute("UPDATE tool_calls SET status='waiting' WHERE id=?", (tool_id,))
                    return tool_id, 'waiting', {'approval_required': True}, tool.return_mode
                if approval['status'] == 'pending':
                    return tool_id, 'waiting', {'approval_required': True}, tool.return_mode
                if approval['status'] == 'denied':
                    result = {'error': 'User denied approval'}
                    self._finish(tool_id, 'denied', result)
                    return tool_id, 'denied', result, tool.return_mode
            self.store.execute("UPDATE tool_calls SET status='executing' WHERE id=?", (tool_id,))
            result = tool.handler(execution, **call.arguments)
            self._finish(tool_id, 'completed', result)
            return tool_id, 'completed', result, tool.return_mode
        except Exception as error:
            result = {'error': str(error), 'error_type': type(error).__name__}
            self._finish(tool_id, 'failed', result)
            return tool_id, 'failed', result, 'resume_agent'

    def _finish(self, tool_id, status, result):
        self.store.execute('UPDATE tool_calls SET status=?,result=?,finished_at=CURRENT_TIMESTAMP WHERE id=?',
                           (status, json.dumps(result, ensure_ascii=False), tool_id))


def object_schema(properties=None, required=None):
    return {'type': 'object', 'properties': properties or {}, 'required': required or [], 'additionalProperties': False}


def register_safe_tools(registry, workspace):
    registry.register(ToolDefinition('escalate', 'Pass a request requiring judgment to the Personal Agent.',
        object_schema(), lambda execution: {'route_to': 'personal'}, return_mode='fire_and_forget'))
    registry.register(ToolDefinition('current_time', 'Get the current UTC time.', object_schema(),
        lambda execution: {'utc': datetime.now(timezone.utc).isoformat()}))
    registry.register(ToolDefinition('read_file', 'Read a UTF-8 file inside workspace.',
        object_schema({'path': {'type': 'string', 'minLength': 1}}, ['path']),
        lambda execution, path: workspace.read(path)))
    registry.register(ToolDefinition('write_note', 'Create a new Markdown note in workspace, with user approval.',
        object_schema({'path': {'type': 'string', 'minLength': 1}, 'content': {'type': 'string'}}, ['path', 'content']),
        lambda execution, path, content: workspace.write_note(path, content), approval_policy='required'))
