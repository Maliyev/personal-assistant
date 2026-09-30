# Configuration

## 1. Rule

### LOCKED

Settings that reasonably need tuning must live in configuration rather than hidden constants.

A human-readable Markdown reference must exist next to the configuration and explain every setting.

The configuration system should be simple in V0.

## 2. Suggested layout

```text
config/
  config.json
  agents/
    tier1.json
    personal.json
    ...
  CONFIG.md
```

This layout is a recommendation, not a reason to over-engineer a config framework.

Agent profiles may also be persisted in SQLite while seed/default profiles originate from config files. Pick one clear source-of-truth flow for V0 and document it.

## 3. Settings that must be configurable

At minimum:

### Runtime

- global max tool-loop steps;
- default timeouts;
- background/async execution limits if implemented.

Default V0 max tool-loop steps:

`10`

### Providers

- provider name;
- model name;
- model parameters;
- API base/options when needed.

Secrets do not belong in committed config.

### Retry

- max attempts;
- max total wait;
- base backoff;
- max backoff;
- jitter behavior.

### Context

Separate settings for Personal Agent and experts:

- active transcript/context threshold;
- maximum context size;
- tool-result insertion limit;
- number/size limits for memory layers if needed.

### Fast Memory Manager

- enabled/disabled;
- model/provider used for memory maintenance;
- context pressure threshold;
- periodic maintenance interval.

Earlier intended default behavior: around once per hour, but this is a tunable value rather than a locked constant.

### Expert light compaction

- threshold;
- model/provider used for summary;
- amount of recent raw transcript retained.

### Slow Memory Manager

Future/stub settings:

- enabled;
- schedule;
- model/provider.

### Scheduler

- poll/tick frequency or equivalent execution config.

## 4. Secrets

API keys/tokens belong in environment variables or a dedicated secrets mechanism.

Do not commit secrets.

`.env` files are ignored by Git.

## 5. Config documentation

`CONFIG.md` in the real repository should document for each field:

- name/path;
- type;
- default;
- allowed values;
- what changing it does;
- warnings/cost implications when relevant.

Do not require reading source code to understand a tuning parameter.
