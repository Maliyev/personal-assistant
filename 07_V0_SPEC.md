# V0 Specification

## 1. Purpose

V0 is an architectural prototype with real persistence, routing, provider abstraction, context management and basic memory.

It is intentionally not a full personal assistant product.

The point is to prove that the system skeleton works correctly before adding expensive integrations and autonomous behavior.

## 2. What must be real in V0

### Persistence

- SQLite database;
- migrations/schema initialization;
- agents;
- sessions;
- messages;
- runs;
- api_calls;
- tool_calls;
- approvals;
- scheduled_jobs;
- memory_items;
- files index.

### Provider architecture

- generic LLM request/response contract;
- Provider Gateway;
- at least one real provider adapter;
- shared retry/error layer;
- API-call persistence.

A second adapter may be a stub if necessary, but the core must not depend on the first provider.

### Agent architecture

- Agent Manager;
- configurable Tier 1 agent;
- configurable Tier 2 Personal Agent;
- support for expert profiles;
- internal sessions.

### Context architecture

- Context Service;
- separate Personal-Agent context policy;
- separate expert context policy;
- active transcript;
- memory-layer insertion;
- tool definitions;
- current input.

### Memory

- persistent raw history;
- active state;
- short-term memory;
- Fast Memory Manager invocation after response when threshold is exceeded;
- basic periodic maintenance hook;
- expert light-compaction hook.

Slow Memory, long-term RAG and advanced promotion can remain stubs.

### Runtime

- runs;
- tool loop;
- max 10 steps;
- Tier 1 -> Tier 2 escalation;
- tool execution;
- approval waiting state;
- expert delegation path;
- background/asynchronous expert capability skeleton.

### Tools

At least 1–2 real, safe tools should exist so the runtime can be exercised end-to-end.

Other future tools may be stubs.

Do not implement destructive PC automation merely to prove the architecture.

### Scheduler

Provide the skeleton and persistence model.

At minimum, proving one one-time wakeup path is desirable if implementation cost remains small.

## 3. What may be stubbed in V0

- WhatsApp;
- Instagram;
- full Telegram integration;
- ActivityWatch;
- PC automation;
- browser automation;
- OSINT;
- RAG/vector database;
- Slow Memory intelligence;
- social-message monitoring;
- voice/STT;
- AI approval judge;
- multi-device sync;
- advanced fallback routing;
- rich UI/dashboard.

The interface boundaries should exist where already defined, but do not implement fake complexity.

## 4. Main user session

There is one logical infinite session:

`Magerram <-> Personal Agent`

The database retains all raw messages.

The model sees only:

- stable prefix;
- allowed memory layers;
- active transcript;
- current input;
- retrieved memory later;
- tools.

Fast Memory prevents the active context from growing forever.

## 5. Tier 1 behavior

Tier 1 sees a small context.

It decides whether to:

- perform a simple action;
- escalate to Tier 2.

Do not let Tier 1 become a second Personal Agent.

## 6. Tier 2 behavior

Tier 2:

- talks to Magerram;
- has the layered personal context;
- can use tools;
- can delegate work;
- can inspect/report background expert status when that interface exists.

## 7. Expert behavior

Default expert:

- gets a new session for a new independent job;
- can continue an existing session when a session id is supplied;
- uses light compaction;
- may be long-running/asynchronous;
- reports useful completion state/results back into the system.

## 8. V0 acceptance scenarios

The implementation should pass mental and executable versions of these scenarios.

### Scenario A — infinite conversational continuity

1. User says: "I am currently working on X."
2. Conversation continues.
3. Enough messages accumulate to trigger Fast Memory.
4. Fast Memory runs after the current response.
5. Old raw messages remain in SQLite.
6. Relevant X state remains accessible through Active/Short-term memory.
7. User later asks: "What was I working on?"
8. Personal Agent answers using maintained state rather than replaying the full history.

### Scenario B — Tier 1 routing

1. User says a clearly simple command.
2. Tier 1 handles/routes it without loading the full Personal Agent context.

Then:

1. User asks a judgment-heavy personal question.
2. Tier 1 escalates to Tier 2.
3. Tier 2 receives its richer personal context.

### Scenario C — tool loop

1. Agent requests a tool.
2. Tool call is persisted.
3. Policy checks it.
4. Tool executes.
5. Result returns through Context Service.
6. Same run continues.
7. Final answer is produced.
8. Loop cannot exceed 10 steps.

### Scenario D — approval

1. Agent requests an approval-gated tool.
2. Tool is not executed immediately.
3. Approval row is stored as pending.
4. System can restart.
5. Pending approval still exists.
6. Approval/denial resumes the correct flow.

### Scenario E — provider failure

1. Provider returns temporary error.
2. Adapter normalizes it.
3. Shared retry layer retries according to config.
4. API attempt/result is observable.

Then test permanent error:

1. Provider returns auth/invalid request.
2. System does not retry forever.
3. Exact normalized error is persisted/surfaced.

### Scenario F — expert delegation

1. Personal Agent delegates to Expert A with no session id.
2. New internal session is created.
3. Expert gets a child run.
4. Personal Agent is not permanently blocked.
5. Expert produces result.
6. Result/status can later be surfaced back to Personal Agent.

### Scenario G — continuing expert session

1. Personal Agent delegates to Expert A and creates session S.
2. Later it sends another message with session S.
3. Expert receives previous session history/light summary plus new input.
4. No new unrelated session is created.

### Scenario H — restart durability

1. System has active sessions, memory and history.
2. Process exits.
3. Process restarts.
4. Main session id, messages and memory remain.
5. Conversation continues normally.

## 9. Explicit non-goals

V0 is not judged by:

- production-grade UI;
- huge number of tools;
- real WhatsApp access;
- perfect memory intelligence;
- autonomous PC control;
- fully proactive assistant behavior.

It is judged by whether the architecture is real, traceable, persistent and extensible.
