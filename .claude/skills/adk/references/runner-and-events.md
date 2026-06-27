# Runner, Events, and Context Objects

## `Runner`

The `Runner` orchestrates execution: it ties an `Agent` to a `SessionService` (and optionally `ArtifactService`/`MemoryService`), creates the `InvocationContext` for each call, and yields a stream of `Event`s.

```python
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

session_service = InMemorySessionService()
runner = Runner(agent=my_root_agent, app_name="my_app", session_service=session_service)

async for event in runner.run_async(user_id="user123", session_id="session456", new_message=user_message):
    print(event.stringify_content())
```

Optional services are passed the same way: `artifact_service=...`, `memory_service=...`.

There is also a synchronous `runner.run(...)` (used in some non-async snippets) and `InMemoryRunner` which bundles an in-memory session service for quick scripts/tests.

### Basic interaction helper pattern

```python
from google.genai import types

async def call_agent_async(query, runner, user_id, session_id):
    content = types.Content(role="user", parts=[types.Part(text=query)])
    final_response_text = "(No final response)"
    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
        if event.is_final_response() and event.content and event.content.parts:
            final_response_text = event.content.parts[0].text
    return final_response_text
```

## Events

An `Event` (`google.adk.events.Event`) is an immutable record of one occurrence in the invocation: user message, agent reply, tool call/result, state change, or control signal. It builds on `LlmResponse` plus ADK metadata:

- `author` — `'user'` or the agent name that produced it.
- `invocation_id` — id for the entire request-to-final-response cycle.
- `id` — unique id for this event.
- `timestamp`
- `content` — `types.Content`, may hold text, function calls, or function responses.
- `partial` — `True` if this is a streaming chunk with more text to come.
- `actions` — an `EventActions` payload (see below).
- `branch` — hierarchy path in multi-agent systems.

### Identifying event type

```python
async for event in runner.run_async(...):
    print(f"Event from: {event.author}")
    if event.content and event.content.parts:
        if event.get_function_calls():
            print("  Type: Tool Call Request")
        elif event.get_function_responses():
            print("  Type: Tool Result")
        elif event.content.parts[0].text:
            print("  Type: Streaming Text Chunk" if event.partial else "  Type: Complete Text Message")
    elif event.actions and (event.actions.state_delta or event.actions.artifact_delta):
        print("  Type: State/Artifact Update")
```

### Extracting function calls / responses

```python
calls = event.get_function_calls()
for call in calls:
    print(call.name, call.args)  # args is a dict

responses = event.get_function_responses()
for response in responses:
    print(response.name, response.response)  # response.response is a dict
```

### `EventActions` — side effects and control flow

- `event.actions.state_delta` — dict of `{key: value}` state changes applied by this event.
- `event.actions.artifact_delta` — dict of `{filename: version}` artifacts saved.
- `event.actions.transfer_to_agent` (str) — control should pass to the named agent (LLM-driven delegation).
- `event.actions.escalate` (bool) — terminate a `LoopAgent`.
- `event.actions.skip_summarization` (bool) — don't let the LLM summarize this tool result.

```python
if event.actions:
    if event.actions.state_delta:
        print(f"  State changes: {event.actions.state_delta}")
    if event.actions.transfer_to_agent:
        print(f"  Signal: Transfer to {event.actions.transfer_to_agent}")
    if event.actions.escalate:
        print("  Signal: Escalate (terminate loop)")
```

Checking `event.is_final_response()` is the standard way to know when an agent's turn is fully done and `event.content` holds the final text.

## Context object hierarchy

ADK exposes "flavors" of context, each appropriate to where it's used:

- **`InvocationContext`** — passed as `ctx` to an agent's `_run_async_impl`/`_run_live_impl`. Most comprehensive: direct access to `session` (state + events), `agent`, `invocation_id`, `user_content`, and service references (`artifact_service`, `memory_service`, `session_service`). Can set `ctx.end_invocation = True`.

  ```python
  from google.adk.agents import BaseAgent
  from google.adk.agents.invocation_context import InvocationContext
  from google.adk.events import Event
  from typing import AsyncGenerator

  class MyAgent(BaseAgent):
      async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
          agent_name = ctx.agent.name
          session_id = ctx.session.id
          yield  # ... event ...
  ```

- **`ReadonlyContext`** — read-only view of `invocation_id`, `agent_name`, `state`. Used in `InstructionProvider` functions (instructions defined as a callable rather than a static string).

  ```python
  from google.adk.agents.readonly_context import ReadonlyContext

  def my_instruction_provider(context: ReadonlyContext) -> str:
      user_tier = context.state.get("user_tier", "standard")
      return f"Process the request for a {user_tier} user."
  ```

- **`Context`** (formerly `CallbackContext`, kept as an alias) — passed to agent/model lifecycle callbacks (`before_agent_callback`, `after_agent_callback`, `before_model_callback`, `after_model_callback`). Adds mutable `state`, `load_artifact(filename)`, `save_artifact(filename, part)`, and `user_content`.

  ```python
  from google.adk.agents.context import Context
  from google.adk.models import LlmRequest
  from typing import Optional
  from google.genai import types

  def my_before_model_cb(context: Context, request: LlmRequest) -> Optional[types.Content]:
      call_count = context.state.get("model_calls", 0)
      context.state["model_calls"] = call_count + 1
      return None  # allow the model call to proceed
  ```

- **`ToolContext`** — passed to function-tool implementations and tool callbacks. Superset of `Context` adding `request_credential`/`get_auth_response` (auth flows), `list_artifacts()`, `search_memory(query)`, `function_call_id`, and `actions`. See `tools.md`.

### Common context tasks

```python
# Read app/user/temp state
api_endpoint = tool_context.state.get("app:api_endpoint")
last_result = context.state.get("temp:last_api_result")

# Identifiers for logging
agent_name = tool_context.agent_name
inv_id = tool_context.invocation_id
func_call_id = getattr(tool_context, "function_call_id", "N/A")

# Initial user input for this invocation
if context.user_content and context.user_content.parts:
    initial_text = context.user_content.parts[0].text
```
