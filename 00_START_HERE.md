# Personal Assistant V0 — Start Here

This folder is the architectural specification for Magerram Aliyev's Personal Assistant V0.

The goal of V0 is **not** to build every final feature. The goal is to build the real architectural skeleton now, with simple or stub implementations where appropriate, so future modules can be upgraded without rewriting the system.

## Decision status language

The documents use three levels:

- **LOCKED** — this was explicitly decided. Do not change it during implementation without discussing it with Magerram first.
- **V0 DECISION** — use this exact approach for V0. It may evolve later, but it should not be redesigned during initial implementation.
- **OPEN / FUTURE** — the high-level idea is known, but the exact design was intentionally not fixed yet. Do not invent a complex permanent architecture for it.

If two documents appear to conflict, stop and ask rather than silently choosing a new architecture.

## Read order

1. `01_ARCHITECTURE.md`
2. `02_RUNTIME.md`
3. `03_MEMORY_AND_CONTEXT.md`
4. `04_DATABASE.md`
5. `05_LLM_TOOLS_PROVIDERS.md`
6. `06_CONFIG.md`
7. `07_V0_SPEC.md`
8. `08_IMPLEMENTATION_GUIDE.md`

## Core V0 goal

A real minimal system should be able to:

- accept a user message;
- pass it through the Tier 1 fast agent;
- either handle a simple request or escalate to the Tier 2 Personal Agent;
- maintain one logical infinite user↔Personal-Agent session;
- build context through a dedicated Context Service;
- preserve raw conversation history in SQLite;
- maintain a small active transcript and memory layers;
- call an LLM through provider-independent request/response types;
- use a provider adapter rather than calling a provider directly from runtime code;
- execute generic tools through a Tool Registry + Tool Runtime;
- enforce a global maximum of 10 tool-loop steps per agent turn;
- support approval-gated tools;
- create internal agent↔agent sessions;
- create asynchronous expert work without blocking the Personal Agent;
- persist API calls, tool calls, runs, messages, sessions, memory, approvals and scheduler state;
- survive restart without losing the logical conversation or persistent state.

Many integrations may be stubs in V0. The architectural boundaries should be real.
