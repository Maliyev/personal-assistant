# Implementation Guide and Roadmap

## 1. Main instruction to the coding agent

Implement the agreed architecture rather than replacing it with a simpler monolithic chatbot.

At the same time, do not over-engineer internal abstractions beyond what V0 actually needs.

When a decision in these documents is marked LOCKED, do not silently redesign it.

When an area is marked OPEN/FUTURE, implement only the minimum interface/stub needed by V0.

## 2. Architectural philosophy

### Full architecture, cheap implementations

The long-term system may eventually use many models and many background calls.

V0 should preserve the boundaries now, but use simple implementations.

Examples:

- real Context Service, simple memory algorithm;
- real Tool Runtime, only 1–2 real tools;
- real Scheduler interface/table, minimal scheduler behavior;
- real provider abstraction, only one fully implemented adapter at first;
- real expert session/run model, minimal expert behavior;
- real Slow Memory interface, stub internals.

Do not collapse boundaries simply because V0 functionality is small.

### Replaceable modules

A future upgrade should be able to replace:

- Fast Memory implementation;
- model used by Tier 1;
- provider adapter;
- retry policy;
- tool handler;
- expert implementation;
- telemetry processor;

without rewriting unrelated runtime code.

### Minimize context and cost

Do not blindly send:

- entire conversation history;
- entire workspace;
- all memories;
- all files;
- large tool outputs.

Context should contain only what the target agent needs.

### Filesystem discipline

Large user/workspace files remain files.

SQLite stores metadata and system state.

### Observability

Every important runtime action should be reconstructable from persistence/logs:

- which agent ran;
- which session;
- which API calls;
- which tools;
- which child run;
- failure reason.

## 3. Recommended implementation phases

### Phase 0 — project skeleton

Create clean modules/interfaces for:

- config;
- database;
- models/types;
- agents;
- context;
- memory;
- providers;
- runtime;
- tools;
- approvals;
- scheduler;
- workspace.

Do not implement all advanced logic yet.

Ensure application starts.

### Phase 1 — database and configuration

Implement:

- schema/migrations;
- repository/helper layer;
- config loader;
- `CONFIG.md` based on actual fields;
- agent seed/loading flow.

Verify database persists across restart.

### Phase 2 — provider abstraction

Implement:

- generic request/response types;
- normalized errors;
- Provider Gateway;
- one real adapter;
- shared retry policy;
- api_calls logging.

Test direct generic LLM call without agent runtime first.

### Phase 3 — Agent Manager + Context Service

Implement:

- AgentProfile loading;
- prompt-file loading;
- agent tool selection;
- basic Personal context builder;
- basic Tier 1 context builder;
- expert light-context builder.

No duplicated manual prompt assembly in multiple agents.

### Phase 4 — sessions/messages/runs

Implement:

- main infinite user session creation/reuse;
- internal sessions;
- message persistence;
- run creation/status transitions;
- parent_run relationships.

### Phase 5 — core runtime

Implement:

- user input -> Tier 1;
- Tier 1 -> Tier 2 escalation;
- LLM call loop;
- final message persistence;
- max 10 tool-loop steps.

Get ordinary text conversation working end-to-end.

### Phase 6 — Tool Registry + Tool Runtime

Implement:

- generic definitions;
- argument validation;
- tool_call persistence;
- return modes;
- 1–2 safe real tools;
- several stub tools if useful for architectural testing.

### Phase 7 — approvals

Implement:

- policy evaluation;
- pending approval persistence;
- resume/deny path.

A simple CLI approval transport is enough for V0.

### Phase 8 — Fast Memory

Implement:

- context-pressure detection;
- post-response trigger;
- memory model call through normal provider layer;
- structured result sufficient to choose transcript ranges and update active/short layers;
- active transcript filtering;
- periodic maintenance hook.

Do not delete raw messages.

### Phase 9 — expert delegation

Implement:

- generic send/delegate capability;
- create/continue internal session;
- child runs;
- asynchronous/background execution skeleton;
- result/status persistence.

The Personal Agent must remain available.

### Phase 10 — scheduler

Implement minimal persisted one-time scheduling.

Scheduled activation should enter the same Runtime as normal agent activation.

### Phase 11 — integration tests / scenario tests

Run the scenarios in `07_V0_SPEC.md`.

Only after these scenarios work should V1 integrations be added.

## 4. Suggested module boundaries

Exact filenames are not locked, but responsibilities should remain separate.

Possible structure:

```text
src/
  config/
  db/
  agents/
  context/
  memory/
  providers/
  runtime/
  tools/
  approvals/
  scheduler/
  workspace/
  main.py

prompts/
config/
workspace/
data/
tests/
```

Do not create dozens of tiny abstractions without benefit.

## 5. Testing priorities

Prioritize tests for boundaries, because that is where this architecture can fail.

Important tests:

- provider adapter normalization;
- retryable vs non-retryable error;
- session continuation;
- parent/child runs;
- Tier 1 escalation;
- tool-loop limit;
- approval persistence;
- Fast Memory runs after response, not before;
- raw messages survive compaction;
- expert light compaction;
- restart durability.

## 6. Things the coding agent must not do automatically

Do not:

- redesign the agreed architecture;
- introduce a framework just because it is popular;
- make provider-specific types the core data model;
- merge Context Service and Memory Manager into one giant service;
- turn every future idea into a real V0 implementation;
- create a task table or agent_jobs table;
- delete raw conversation history during compaction;
- block the Personal Agent on long-running expert work;
- put file bytes in SQLite;
- hard-code tuning values that belong in config;
- retry provider errors forever;
- exceed the 10-step tool loop;
- run Git commands if AGENTS.md forbids them.

## 7. Expected result of V0

At the end of V0, Magerram should be able to run the application, have a continuing Personal-Agent conversation, observe Tier 1 routing, maintain real persisted memory/context state, call tools, test approvals, inspect API/tool/run traces, restart the process, and continue without losing state.

That is enough.

Do not chase V1 features until this skeleton survives real use.
