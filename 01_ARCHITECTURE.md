# Architecture

## 1. System purpose

The Personal Assistant is a long-running personal agent system, not a single chatbot session.

The LLM is a reasoning component inside the system. Python owns the runtime, state, persistence, permissions, scheduling, context construction, tools and provider integration.

The architecture must stay modular enough that an individual component can later be replaced with a more capable and more expensive implementation without rewriting unrelated parts of the system.

## 2. Core engineering principles

### LOCKED — provider independence

No core runtime code may depend directly on Gemini, OpenRouter, or another provider-specific request/response format.

All LLM interaction must go through:

`Runtime -> Provider Gateway -> Provider Adapter -> Provider API`

Adapters translate between the system's generic LLM contract and the provider-specific API.

### LOCKED — agents are profiles, not hard-coded prompt pipelines

An agent is a configurable profile, not a special `agent.py` file with hand-built prompt logic.

An agent profile contains or references:

- model/provider configuration;
- system prompt files;
- tools/capabilities;
- context policy;
- memory policy;
- runtime/model settings.

`Agent Manager` stores and loads these profiles.

### LOCKED — context construction is a separate service

`Context Service` is the low-level component that physically builds the input sent to an LLM.

It may combine:

- static prompt files;
- memory layers;
- active transcript;
- current input;
- tool definitions;
- expert working summary;
- other dynamic context allowed by the agent's context policy.

Agent-specific code must not manually rebuild context in multiple places.

### LOCKED — memory management is separate from context construction

`Context Service` reads/assembles context.

`Memory Manager` decides how information moves between memory layers and what can leave the active transcript.

They are different responsibilities.

### LOCKED — shared generic tools

There is one generic Tool Registry. Tool definitions are provider-independent.

Provider adapters convert generic tool definitions into provider-specific tool schemas.

Actual tool execution is handled by Tool Runtime, not by provider adapters.

### LOCKED — persistence

SQLite is the V0 structured source of truth.

Large files and workspace documents are stored on the filesystem, not as SQLite BLOBs.

SQLite may index those files.

Prompts are normal files under a prompts directory.

### LOCKED — raw history is never destroyed by compaction

Conversation compaction only affects what is loaded into model context.

Raw messages remain stored in SQLite.

## 3. Agent hierarchy

### Tier 1 — Fast Agent / Router

Purpose:

- very cheap;
- very fast;
- can be called many hundreds of times per day in the future;
- handles routing and very simple actions;
- should escalate when the request needs real judgment.

Typical examples:

- "open Spotify";
- "close it";
- simple tool dispatch;
- classify whether the Personal Agent is needed.

Tier 1 should not give important life advice merely because it can produce text.

### Tier 2 — Personal Agent / Orchestrator

This is the main agent that represents the assistant to Magerram.

It:

- communicates directly with Magerram;
- has the richest personal context;
- uses the layered memory system;
- understands preferences and communication style;
- can delegate work to experts;
- can query status/results of expert work;
- is logically always available and must not be blocked waiting for a long-running expert.

The user-facing session with this agent is one logical infinite session.

### Tier 3 — Expert / Deep Worker

Experts perform heavier or specialized work.

Examples later may include:

- research;
- social/messaging;
- computer control;
- OSINT;
- coding;
- document analysis.

Experts can have their own sessions. A new task may create a new expert session; a continuing task may continue an existing session.

### Tier 4 — future

Reserved for rare frontier/deep-review work. Not part of V0 implementation.

## 4. Major services

### Agent Manager

Responsibilities:

- store/load agent profiles;
- create/update profiles through a stable interface;
- expose a resolved `AgentProfile` object to runtime.

It does not build the final LLM context.

### Context Service

Responsibilities:

- assemble the actual model input;
- apply the agent's context policy;
- include allowed memory layers;
- include active transcript;
- include tools/capabilities;
- enforce context-size limits;
- truncate or summarize tool results before reinsertion if needed;
- record context-related statistics.

It should be relatively low-level and deterministic where possible.

### Memory Manager

Two conceptual parts:

- Fast Memory Manager;
- Slow Memory Manager.

V0 implements the fast path meaningfully and may keep the slow path minimal/stubbed.

Detailed behavior is defined in `03_MEMORY_AND_CONTEXT.md`.

### Provider Gateway

Responsibilities:

- accept a generic `LLMRequest`;
- select the configured provider adapter;
- pass the request through the shared retry/error policy;
- return a normalized `LLMResponse`.

### Provider Adapter

One adapter per provider.

Responsibilities:

- convert generic request -> provider request;
- make the real API call;
- parse provider response;
- map provider errors into normalized errors;
- expose usage/finish metadata.

Retry policy is **not duplicated inside every adapter**.

### Retry / Reliability Layer

One shared retry policy for all providers.

It decides whether to retry based on normalized error type.

Transient errors may retry.

Permanent/request errors must not be hammered repeatedly.

### Tool Registry

Stores generic tool definitions.

### Tool Runtime

Executes actual tool handlers.

All tool calls flow through policy/approval before execution.

### Approval Policy

Determines whether a tool call:

- is allowed automatically;
- requires approval;
- is denied.

Pending approvals must survive restart.

### Scheduler

Stores one-time and recurring future wakeups.

A scheduled wakeup ultimately becomes a normal agent activation and uses the same runtime path as any other activation.

### Workspace

Filesystem-owned working area where the assistant may later:

- store user files;
- generate files;
- create scripts;
- keep project material;
- keep documents.

SQLite indexes workspace files so agents do not need to repeatedly scan the full filesystem.

### Telemetry / Activity ingestion — FUTURE

Raw ActivityWatch/device/browser streams should not be fed directly to memory agents.

Future flow:

`source adapters -> normalized events -> activity processor -> active/short-term memory`

Not required for V0.

## 5. Inter-agent communication

### LOCKED high-level behavior

Agents may communicate with other agents.

The orchestrator and each expert should expose a generic communication capability rather than a separate bespoke tool for every message type.

For V0, inter-agent content may remain primarily textual.

Runtime metadata should still preserve:

- sender agent;
- target agent;
- session;
- parent run relationship.

Structured JSON communication can be introduced later without redesigning the session/runtime model.

### Asynchronous expert behavior

The Personal Agent must not block for long-running expert work.

A delegation creates/continues an internal session and creates a child run for the expert.

The Personal Agent may continue operating.

Expert completion can later be surfaced back to the Personal Agent through normal system/event plumbing.

## 6. Future capabilities intentionally outside V0

The architecture should leave room for:

- Telegram;
- WhatsApp;
- Instagram;
- social-message monitoring;
- PC control;
- remote PC access;
- ActivityWatch;
- phone telemetry;
- browser history;
- internet/browser automation;
- RAG;
- OSINT;
- voice/STT;
- AI approval judge;
- MCP integrations;
- multiple devices;
- richer proactive behavior.

Do not implement permanent complex versions of these in V0 unless explicitly requested.
