# Memory and Context

## 1. Separation of responsibilities

### LOCKED — Context Service

Context Service builds the actual context sent to the model.

It does not decide long-term memory strategy on its own.

### LOCKED — Memory Manager

Memory Manager decides how conversational information is retained, summarized, promoted, or removed from active model context.

Raw database history is not deleted by compaction.

## 2. Main Personal Agent memory model

The Personal Agent uses layered memory.

### Layer 1 — Stable Prefix

Very stable information.

Contains:

- core system instructions;
- important information about Magerram;
- communication style;
- permanent preferences;
- global behavioral rules;
- capabilities/tool guidance that should remain stable.

Expected size may eventually be roughly 1k–5k tokens and can grow higher if justified, but V0 should keep it reasonably small.

The stable prefix should be kept stable where possible to improve provider-side prompt caching.

### Layer 2 — Middle-term Memory

Information relevant for weeks or months.

Examples:

- preparing for midterms;
- currently building Personal Assistant;
- an ongoing project phase;
- an important multi-week commitment.

Usually a relatively small list, not a full transcript.

### Layer 3 — Short-term Log

A compact representation of recent days.

This is not simply "the last N messages."

It should look more like chronological event/state entries.

Example:

- 09:20 — continued V0 architecture work.
- 10:10 — decided that user↔Personal-Agent is one infinite logical session.
- 11:30 — waiting for X response.

It may cover roughly 1–2 days depending on configuration.

### Layer 4 — Active State

What is happening now.

Typical horizon:

- minutes;
- roughly 1–2 hours.

Examples:

- current task;
- unresolved references;
- recently opened app;
- "waiting for Rashad's reply";
- current working context.

This allows follow-ups such as:

"open Spotify"
then
"close it"

### Layer 5 — Retrieved Memory

Query-specific memory retrieved when needed.

Future RAG may provide:

- person-specific history;
- project details;
- old decisions;
- rare personal facts.

Not required to be fully implemented in V0.

### Layer 6 — Current Input

The current user/event input should remain distinct from Active State.

Active State describes current context.

Current Input is the new thing that just arrived.

## 3. Active Transcript

The system also keeps a small raw transcript window.

For the Personal Agent, there is one logical infinite conversation, but the model does **not** receive the entire raw history.

The prompt includes only the currently relevant active transcript plus memory layers.

Raw messages remain in SQLite forever unless explicit retention policy is introduced later.

## 4. Fast Memory Manager

### LOCKED trigger timing

If the active context/transcript exceeds a configured threshold, Fast Memory processing occurs **after** the user's current message has been answered.

The user should not have to wait for compaction before getting the current answer.

### LOCKED behavior

Fast Memory Manager receives the relevant old transcript/context and decides what information should:

- remain in active transcript;
- become/update Active State;
- become/update Short-term Log;
- leave the active model context.

It may decide to keep material if it is still relevant.

Compaction is not a blind "drop oldest 10 messages" algorithm.

### Periodic maintenance

Fast Memory Manager may also run on a configurable periodic interval.

Earlier design target: approximately hourly, configurable.

A periodic pass may examine:

- Active State;
- Short-term data;
- timestamps;
- active conversation context.

It may move older active-state information into short-term memory.

## 5. Daily activity log

### V0/FUTURE-compatible decision

For each day, maintain a detailed `.md` activity/memory log on disk.

Fine-grained Activity State entries can be appended here.

When information is later summarized into Short-term Memory, the detailed daily log is not destroyed.

This gives:

- compact model context;
- retained fine-grained historical record.

## 6. Slow Memory Manager

The Slow Memory Manager performs deeper consolidation.

It is expected to run much less frequently, for example once per day/night.

Responsibilities later:

- promote meaningful information from short-term/active layers into middle-term memory;
- create durable long-term memories;
- archive old information;
- add/index knowledge for RAG;
- resolve or update old memories.

V0 may implement this as a stub or very simple first pass.

## 7. Expert-agent context

Experts use a simpler memory strategy by default.

### LOCKED default

Expert sessions use lightweight compaction rather than the full personal layered-memory system.

When an expert transcript crosses its configured threshold:

- old content is summarized into an expert working summary;
- recent messages remain raw;
- work continues in the same expert session.

Expert threshold is configurable separately from the Personal Agent threshold.

### Expert statefulness

Experts are not required to be stateless.

A multi-step expert job may keep a session across multiple activations.

A new independent task may create a new expert session.

Results/knowledge that must persist across expert sessions may later be stored in an expert-specific memory/workspace file.

## 8. Tier 1 context

Tier 1 should stay cheap.

Default context:

- stable/router prompt;
- capabilities/tool descriptions;
- reduced/compressed short-term information;
- Active State;
- current input.

Normally exclude:

- full middle-term memory;
- full Retrieved Memory;
- large personal history.

If deeper memory is needed, escalation to Tier 2 is appropriate.

## 9. Memory data storage

For V0, structured memory items live in SQLite.

The current minimal memory table intentionally does not include confidence/source/source_id.

Do not spend LLM tokens generating metadata that V0 does not use.

Future memory provenance can be added later if a real need appears.

## 10. Telemetry — FUTURE

ActivityWatch, PC state, phone state, browser history and similar streams should not directly flood the LLM context.

Future architecture:

`raw telemetry -> source adapter -> normalized events -> activity processor -> memory`

The Activity Processor should convert high-volume raw events into meaningful statements such as:

- "worked in VS Code on personal-assistant for 45 minutes";
- "switched to YouTube";
- "computer idle for 30 minutes."

Only processed/meaningful data should enter active/short-term memory.
