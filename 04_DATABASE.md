# Database

## 1. General decision

### LOCKED

V0 uses one SQLite database for structured system state.

Do not split V0 into multiple databases without a concrete reason approved by Magerram.

Files themselves live on the filesystem.

SQLite stores file metadata/index information.

## 2. Minimal entities

V0 needs to persist:

- agent profiles;
- sessions;
- messages;
- agent runs;
- LLM API calls;
- tool calls;
- approvals;
- scheduled jobs;
- memory items;
- workspace file index.

## 3. Sessions

### LOCKED conceptual model

A session is a logical conversation/work stream between exactly two participants in V0.

Supported cases:

- user ↔ Personal Agent;
- orchestrator ↔ expert;
- expert ↔ expert.

The same two agents may have multiple different sessions.

The user↔Personal-Agent session is one logical infinite session.

### V0 schema

```text
sessions
- id
- participant_a_type
- participant_a_id
- participant_b_type
- participant_b_id
- created_at
```

Keep this table simple.

Do not introduce a separate `session_participants` table in V0.

## 4. Messages

```text
messages
- id
- session_id
- sender_type
- sender_id
- content
- created_at
```

V0 messages are primarily textual.

Provider-specific raw structures belong in `api_calls`, not `messages`.

Messages are durable raw conversation history.

Compaction does not delete them.

## 5. Runs

### LOCKED definition

One run = one activation/turn of one agent.

A run may contain multiple API calls and tool calls.

A session may contain many runs.

A delegated expert creates another run.

### V0 schema

```text
runs
- id
- session_id
- agent_id
- parent_run_id
- status
- started_at
- finished_at
```

Expected statuses may include:

- running;
- waiting;
- completed;
- failed.

Exact enum/string implementation may remain simple.

`parent_run_id` allows reconstruction of:

Personal Agent run -> Research Expert run -> another child run.

## 6. Agents

### LOCKED V0 design

Keep the SQL table simple and keep flexible agent configuration in JSON.

```text
agents
- id
- name
- config_json
- created_at
```

`config_json` may contain:

- tier;
- provider;
- model;
- prompt file list;
- tool list;
- context policy;
- memory policy;
- runtime/model settings.

Agent Manager parses this into a normal in-memory AgentProfile.

## 7. API calls

Suggested V0 schema:

```text
api_calls
- id
- run_id
- session_id
- agent_id
- provider
- model
- request_json
- response_json
- status
- error_type
- input_tokens
- output_tokens
- cost
- created_at
- finished_at
```

Notes:

- `request_json` stores the actual request/context sent through the provider layer, sufficient for debugging what the model really saw.
- `response_json` stores the actual/normalized response information needed for debugging.
- token/cost fields may be null when a provider does not return the value.
- retries may create multiple API call records or retry-attempt detail inside request logging. Keep the first implementation simple but fully traceable.

## 8. Tool calls

```text
tool_calls
- id
- run_id
- session_id
- agent_id
- api_call_id
- tool_name
- arguments_json
- result
- status
- created_at
- finished_at
```

The table should preserve failed tool attempts as well as successful ones.

## 9. Approvals

Approvals are persistent because a flow may wait across process restart.

```text
approvals
- id
- tool_call_id
- status
- created_at
- resolved_at
```

Expected status values:

- pending;
- approved;
- denied.

Approval transport is separate from this table.

## 10. Scheduled jobs

```text
scheduled_jobs
- id
- target_agent_id
- session_id
- payload
- schedule
- status
- next_run_at
- created_at
```

This must support eventually:

- one-time wakeup;
- recurring wakeup;
- future message to same agent;
- future activation of another agent.

V0 implementation may support only a subset, but do not hard-wire the schema to one-time reminders only.

## 11. Memory items

### LOCKED simplification for V0

Do not add `confidence`, `source`, or `source_id` in V0.

```text
memory_items
- id
- layer
- content
- created_at
- updated_at
```

Known layers:

- active;
- short;
- middle;
- long.

V0 primarily exercises active/short layers.

If ownership/scope becomes necessary for multiple independent memories, add it deliberately rather than guessing a complex design now.

## 12. File index

Files live physically in workspace.

SQLite keeps a lightweight index.

```text
files
- id
- path
- name
- type
- size
- description
- created_at
```

Later optional additions:

- summary;
- tags;
- embedding id;
- indexed_at.

Do not put arbitrary file bytes into SQLite for V0.

## 13. Workspace filesystem

Expected high-level structure may be:

```text
workspace/
  inbox/
  documents/
  projects/
  scripts/
  generated/
  temp/
```

Exact subdirectories are not architecturally locked.

The important decision is:

filesystem stores bytes;
SQLite stores structured metadata/index.

## 14. Deliberate omissions

There is no separate `tasks` table in V0.

There is no `agent_jobs` table.

`runs` represents active agent work/turns.

Do not reintroduce those tables unless a concrete missing requirement appears.
