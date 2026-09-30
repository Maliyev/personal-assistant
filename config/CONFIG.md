# V0 configuration

`config.json` is loaded on startup. Paths are relative to the project root.
Secrets are environment variables; `.env` is optional and never persisted in SQLite.
No third-party Python packages are required.

| Field | Type / default | Allowed values and effect |
|---|---|---|
| paths.database | string, `data/v0.db` | SQLite path. Use a new path for this implementation; legacy chatbot databases are unsupported. |
| paths.workspace | string, `workspace` | Filesystem root for agent files and daily Markdown logs. |
| paths.agent_seeds | string, `config/agents` | Directory of initial JSON profiles. Seeded only if an agent ID is absent in SQLite. |
| runtime.max_tool_steps | integer, 10 | 1–10; maximum executed tool calls per activation, shared by all agents. |
| runtime.request_timeout_seconds | number, 60 | Positive HTTP timeout per attempt. |
| runtime.background_workers | integer, 2 | Positive worker count for expert and memory work. Increasing it permits more simultaneous API calls. |
| runtime.background_queue_limit | integer, 8 | Positive maximum submitted background jobs, including running jobs. |
| retry.max_attempts | integer, 4 | Positive total attempts including the first request. |
| retry.max_wait_seconds | number, 30 | Positive total retry-sleep budget; HTTP timeouts are separate. |
| retry.base_backoff_seconds | number, 1 | Positive first retry delay, doubled each attempt. |
| retry.max_backoff_seconds | number, 10 | Positive cap on each retry delay. |
| retry.jitter | boolean, true | Randomize delays to avoid synchronized retries. |
| providers.gemini.api_key_env | string, `GEMINI_API_KEY` | Environment variable name holding the key; never the key itself. |
| providers.gemini.base_url | HTTPS URL, Google v1beta endpoint | REST endpoint; change only to a trusted endpoint because it receives the API key. |
| scheduler.tick_seconds | number, 5 | Positive polling interval while the terminal is running. |
| memory.periodic_seconds | number, 3600 | Positive interval between memory maintenance checks. |
| memory.slow_enabled | boolean, false | Reserved stub; deep consolidation is not implemented. |

Agent JSON fields:

| Field | Type / seeded defaults | Allowed values and effect |
|---|---|---|
| id, name | strings | Stable ID and display name. |
| tier | integer, 1 / 2 / 3 | Router, Personal Agent or expert. Tier 4 is outside V0. |
| provider | string, `gemini` | Registered provider adapter name. |
| model | string, `gemini-2.5-flash-lite` | Provider model ID. Availability depends on the account/provider; tune before live use. |
| prompts | list of paths | UTF-8 prompt files relative to the project root. |
| tools | list of names | Explicit tool allowlist; unavailable tools are rejected. |
| context.max_characters | positive integer, 12000 / 60000 / 50000 | Hard cap on serialized generic request context. Character counts are conservative application limits, not exact token counts. |
| context.transcript_characters | positive integer, 2000 / 40000 / 35000 | Maximum inserted raw transcript. Current input is never silently discarded. |
| context.tool_result_characters | positive integer, 2000 / 6000 / 6000 | Tool-result insertion cap; complete results stay in SQLite. |
| context.memory_layers | list, router active/short; personal middle/short/active; expert empty | Only listed memory layers enter context. Expert uses its session working summary. |
| memory.enabled | boolean, false / true / true | Enable post-response and periodic maintenance. |
| memory.threshold_characters | positive integer, personal 24000 / expert 20000 | Trigger maintenance after response when active transcript crosses this size. |
| memory.provider, memory.model | strings, `gemini`, `gemini-2.5-flash-lite` | Separate model for maintenance. Maintenance spends additional API calls. |
| memory.recent_messages | positive integer, 6 | Recent raw messages protected during memory processing. |
| model_settings | object, empty | Generic keys: temperature, max_output_tokens, response_json. Adapter maps these to its API. Unsupported keys fail explicitly. |

SQLite agent profiles are the source of truth after seeding. Editing seed files does
not overwrite existing profiles. Use `AgentManager.update(profile)` to change an
existing profile; use a fresh database to exercise new seeds from scratch.
