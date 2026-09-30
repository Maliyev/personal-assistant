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
