# V0 implementation status

Built from scratch using the eight specification files. The old chatbot code was
removed; its database and private environment were not reused or committed.

Completed milestones:

1. SQLite schema/version initialization, configurable agent profiles, stable main
   session, internal sessions, parent/child runs and restart persistence.
2. Generic LLM contracts, shared bounded retry gateway, API attempt persistence,
   Gemini REST adapter including signed continuation parts and function results.
3. Context Service, profile tool allowlists, per-call tool limit, safe workspace
   tools, persisted approvals and resumption/denial after restart.
4. Post-response Fast Memory, active/short layers, preserved raw transcript,
   expert summaries, periodic hook, background delegation, completion reports,
   one-time scheduler and terminal transport.

Verification:

- Offline scenario tests cover persistence, routing, provider failure policy,
  tool cycles and limits, approval restart/denial, memory retention and invalid
  memory output, async expert availability and continuation, expert compaction,
  and one-time scheduler activation through the common runtime.
- `python -m assistant --init-only` starts and initializes the new application.
- Real Gemini request using `gemini-2.5-flash-lite` returned HTTP 404. The user
  selected `gemini-3.1-flash-lite`; live checks for that model remain pending.
- No push or merge was performed. Implementation checkpoints are local commits.

Next validation: run `python -m assistant.smoke` with network access, then exercise
the README examples against the real model. Model routing decisions and memory
quality require live testing beyond controlled offline scenarios.

Known limits are documented in README.md. V1 integrations remain out of scope.
The native Codex project network setting was proposed but its write was rejected;
no `.codex/config.toml` was created. It can be set manually with:

```toml
sandbox_mode = "workspace-write"

[sandbox_workspace_write]
network_access = true
```

Restart Codex after updating its settings. Managed permissions may override local
configuration; effective network access must be checked in the new session.

## Scheduler terminal delivery fix

The scheduler already activated the target agent through Runtime and queued its
response. The terminal only consumed notifications before its blocking input(),
so a finished job could remain invisible until the user submitted another line.
TerminalChannel now runs input on a daemon reader thread and consumes notifications
while waiting for the line, without another model call or another user message.
Regression tests are provided in tests/test_terminal.py. They were not executed;
the user is running tests manually.

## Scheduler activation semantics

Removed the previous uncommitted rescheduling heuristic and relative-delay changes.
New job creation rejects timestamps at or before now. Due jobs still execute after
downtime. Scheduler persists a ScheduledWakeup event with its job ID, scheduled
time, actual trigger time and payload. Context represents it as an event message
with event_type=scheduled_wakeup, including in history, and explicitly tells the
agent to execute the task now rather than treat it as another user scheduling request.
No content classifier or payload equality check is used. New regression tests in
tests/test_scheduler.py have not been run; the user handles test execution.
