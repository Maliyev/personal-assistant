"""Provider-independent model contracts."""
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    id: str = ''


@dataclass
class Message:
    role: str
    text: str = ''
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_name: str = ''
    tool_call_id: str = ''
    # Adapter-owned opaque continuation metadata (e.g. signed model parts).
    provider_data: dict = field(default_factory=dict)
    # Runtime input origin, independent of the provider's supported chat roles.
    event_type: Literal['scheduled_wakeup'] | None = None


@dataclass
class ScheduledWakeup:
    job_id: int
    scheduled_at: str
    triggered_at: str
    payload: str
    event_type: Literal['scheduled_wakeup'] = 'scheduled_wakeup'


@dataclass
class ToolSchema:
    name: str
    description: str
    input_schema: dict


@dataclass
class LLMRequest:
    agent_id: str
    provider: str
    model: str
    system: str
    messages: list[Message]
    tools: list[ToolSchema] = field(default_factory=list)
    settings: dict = field(default_factory=dict)


@dataclass
class LLMResponse:
    text: str = ''
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = 'stop'
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw_provider_response: dict = field(default_factory=dict)
    continuation: Message | None = None
    api_call_id: int | None = None


class ProviderError(RuntimeError):
    def __init__(self, kind, message, retryable=False, raw=None):
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.raw = raw


def restore_message(data):
    data = dict(data)
    data['tool_calls'] = [ToolCall(**call) for call in data.get('tool_calls', [])]
    return Message(**data)
