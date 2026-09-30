# Runtime

## 1. Core definition

A `run` is one activation/turn of one agent.

A run may contain multiple LLM API calls because tool calls can cause the same agent to continue.

A session may contain many runs.

A child agent activation creates its own run.

## 2. Generic runtime flow

### LOCKED flow

1. An input event arrives.
2. Runtime determines the target agent.
3. A `runs` row is created.
4. Agent Manager loads the target agent profile.
5. Context Service builds the context according to that profile.
6. Provider Gateway receives a generic `LLMRequest`.
7. Provider Gateway selects the provider adapter.
8. Shared Retry/Reliability logic controls retry behavior.
9. Adapter performs the real request and returns a normalized response/error.
10. `api_calls` is updated with technical information and the request/response data.
11. Model output is persisted where appropriate.
12. Runtime checks for tool requests.
13. Tool requests go through policy/approval.
14. Approved tool requests execute through Tool Runtime.
15. Tool results are persisted.
16. If the tool requires the agent to resume, Context Service prepares the next model input and the same run continues.
17. The loop continues until final completion, failure, waiting state, or the global tool-step limit is reached.
18. Run status is updated.

## 3. Tool loop

### LOCKED

Global maximum tool-loop steps for V0:

`10`

This applies to all agents unless architecture is explicitly changed later.

The value must live in configuration, not as a hidden magic number.

If the limit is reached:

- stop further automatic tool execution;
- mark the run appropriately;
- preserve the full trace;
- return/surface a clear failure reason rather than silently looping.

## 4. Tool return modes

Tools have different execution semantics.

The generic tool contract should support at least:

### `resume_agent`

The result must be returned to the same agent and another LLM call should occur.

Examples:

- web search;
- read file;
- query database.

### `fire_and_forget`

The action can complete without fundamentally requiring another LLM call.

Example:

- "open Spotify" in a future PC-control tool.

Runtime may still persist a tool result/status, but should not spend another model call merely to restate obvious success unless the caller needs it.

### `async_result`

The tool starts work that finishes later.

Example:

- delegate a research job to an expert.

The parent agent must not be forced to block.

## 5. Tier 1 user entry

### V0 behavior

Normal direct user text enters through Tier 1.

Tier 1 may:

- answer/handle an explicitly simple action through tools;
- escalate to Tier 2 Personal Agent.

Tier 1 context is intentionally small.

Not every future event must go through Tier 1. For example, a scheduled event that already targets a specific expert can directly activate that agent.

## 6. Tier 2 Personal Agent

The Personal Agent handles:

- real conversation;
- judgment;
- personal reasoning;
- delegation;
- richer tools;
- user-facing final responses.

It uses the main infinite user session.

## 7. Delegation

### LOCKED interface behavior

Delegation conceptually contains:

- target `agent_id`;
- message/task text;
- optional `session_id`.

If `session_id` is absent:

- create a new internal session.

If `session_id` is provided:

- continue that internal session.

### LOCKED asynchronous behavior

The Personal Agent does not wait indefinitely for the expert.

Delegation creates a child run and may continue asynchronously.

`parent_run_id` preserves the execution tree.

The expert may later report completion/result back to the Personal Agent.

## 8. Internal-agent completion

An internal expert should not simply produce an unobserved final answer.

A completed expert workflow should have a clear terminal action, such as:

- report result to the caller/orchestrator;
- persist a result in its session/workspace;
- schedule a future wakeup.

The exact reporting tool/protocol may remain simple in V0.

## 9. Approval flow

Tool call -> Policy evaluation.

If auto-allowed:
- execute immediately.

If approval required:
- create persistent approval state;
- put the relevant flow into a waiting state;
- obtain approval through an approval mechanism;
- on approve, execute;
- on deny, return a denied result to runtime/agent if appropriate.

The approval transport is not hard-coded into the core policy system.

Future transports may include:

- Telegram buttons;
- code words in text;
- voice/STT hooks.

## 10. Retry / error handling

Retry logic is centralized.

Adapters normalize provider errors.

The shared reliability layer decides what to do.

Typical retryable errors:

- temporary 429/rate limit;
- temporary 5xx;
- connection reset;
- timeout;
- transient provider outage.

Typical non-retryable-as-is errors:

- authentication failure;
- permission failure;
- malformed request;
- unsupported tool/schema;
- invalid configuration;
- context overflow requiring context changes rather than identical retry.

Retry must have configurable limits:

- max attempts;
- max total wait;
- backoff;
- jitter.

Never retry forever.

## 11. Scheduler

Any agent may eventually schedule:

- one-time wakeups;
- recurring wakeups;
- a future message to itself;
- a future message/activation for another agent.

At execution time, scheduler produces a normal agent activation.

Scheduled work must use the same runtime/provider/tool/persistence path rather than a separate ad-hoc execution path.
