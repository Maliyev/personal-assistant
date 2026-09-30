# LLM, Tools and Provider Contracts

## 1. Generic LLM contract

### LOCKED

Core runtime must operate on provider-independent request/response objects.

Conceptual request:

```text
LLMRequest
- agent_id
- context/messages
- tools
- model settings
```

Conceptual response:

```text
LLMResponse
- text
- tool_calls[]
- finish_reason
- usage
- raw_provider_response
```

The concrete Python types may be dataclasses, Pydantic models, TypedDicts, or another simple typed representation.

Do not leak Gemini/OpenRouter-specific structures into Runtime or Context Service.

## 2. Provider adapters

Each provider adapter must:

- accept the generic request;
- translate messages/context;
- translate generic tools;
- apply provider-specific auth/config;
- perform the real request;
- parse all supported response shapes;
- normalize tool calls;
- normalize usage;
- normalize finish reason;
- normalize errors.

### Important reliability requirement

Before implementing a provider adapter, inspect that provider's current API documentation and expected error/response formats.

Do not guess error types.

## 3. Shared retry policy

Retry is outside individual provider adapters.

Conceptual flow:

`generic request -> retry wrapper -> adapter -> provider`

Adapter returns either:

- normalized response;
- normalized error.

Retry policy determines:

- retry;
- wait;
- fail;
- future fallback behavior.

V0 does not need sophisticated multi-provider fallback unless requested, but the interface should not prevent it.

## 4. Generic tool definition

### LOCKED concept

Tools use one system-owned schema, not one schema per provider.

Conceptual definition:

```text
ToolDefinition
- name
- description
- input_schema
- approval_policy
- return_mode
- handler
```

Provider adapter translates the tool's public schema into the format expected by the provider.

`handler` is an internal implementation reference, not something sent to the LLM.

## 5. Tool Registry

Responsibilities:

- register tools;
- resolve tool by name;
- expose definitions available to a specific agent;
- reject unknown tools.

Agent profiles specify which tools they may access.

## 6. Tool Runtime

Responsibilities:

- receive normalized tool request;
- validate arguments;
- check policy/approval;
- execute handler;
- record tool-call state;
- return normalized result/error.

Tools should not directly manipulate LLM context.

Their result goes back through Runtime/Context Service.

## 7. Approval policies

At minimum, generic tool metadata should express something equivalent to:

- auto allow;
- approval required;
- deny/unavailable.

Future policy may depend on arguments, user state, target person, channel, etc.

V0 can start simple.

## 8. Tool result size

Tool outputs can be very large.

Before returning tool results to an agent, Context Service must be allowed to:

- truncate;
- summarize;
- store full output externally and provide a reference;
- otherwise reduce context cost.

V0 may begin with a simple character/token cap, but the boundary must exist.

## 9. Inter-agent communication as a tool/capability

Inter-agent communication should fit the generic tool model rather than being an unrelated execution path.

Conceptual inputs:

- target agent;
- message;
- optional existing session id;
- optional execution mode later.

For V0, communication content may be plain text.

Runtime creates/continues the correct session and child run.

## 10. Tool loop

Global V0 maximum:

`10 steps`

This is configured centrally.

A tool call that returns to the same agent counts toward this loop.

The runtime must prevent accidental infinite model↔tool cycles.
