# Callbacks

Callbacks hook into specific points of an agent's execution without modifying ADK itself: `before_agent_callback`/`after_agent_callback`, `before_model_callback`/`after_model_callback`, `before_tool_callback`/`after_tool_callback`.

- **Before/After Agent** — wrap the agent's *entire* processing of one request (deciding to call the LLM, calling tools, assembling the final answer).
- **Before/After Model** — wrap each individual call to the LLM.
- **Before/After Tool** — wrap each individual tool execution.

For security guardrails specifically, prefer ADK **Plugins** over callbacks for better modularity — but callbacks remain the right tool for ad hoc logging, state management, and behavior overrides.

## Registering a callback

```python
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse, LlmRequest
from typing import Optional

def my_before_model_logic(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmResponse]:
    print(f"Callback running before model call for agent: {callback_context.agent_name}")
    return None  # allow the model call to proceed

my_agent = LlmAgent(
    name="MyCallbackAgent",
    model="gemini-2.0-flash",
    instruction="Be helpful.",
    before_model_callback=my_before_model_logic,
)
```

## Control-flow mechanism: the return value matters

- **Return `None`** — allow the framework's default next step (agent logic runs / LLM is called / tool executes). For `after_*` callbacks, returning the just-produced result unchanged also means "continue normally."
- **Return a specific object** — override default behavior:
  - `before_agent_callback` → return `Content`: skip the agent's main logic entirely; the returned `Content` becomes the final output for this turn.
  - `before_model_callback` → return `LlmResponse`: skip the actual LLM call; the returned response is used as if the model produced it. This is the standard guardrail/cache pattern.
  - `before_tool_callback` → return a `dict`: skip the actual tool execution; the dict is used as the tool result.
  - `after_agent_callback` → return `Content`: replaces the agent's just-produced output.
  - `after_model_callback` → return `LlmResponse`: replaces the LLM's response (e.g. sanitizing output, adding disclaimers).
  - `after_tool_callback` → return a `dict`: replaces the tool's result before it goes back to the LLM.

## Guardrail pattern: `before_model_callback`

```python
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse, LlmRequest
from typing import Optional
from google.genai import types

def simple_before_model_modifier(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmResponse]:
    """Inspects/modifies the LLM request or skips the call."""
    last_user_message = ""
    if llm_request.contents and llm_request.contents[-1].role == "user":
        if llm_request.contents[-1].parts:
            last_user_message = llm_request.contents[-1].parts[0].text

    if "BLOCK" in last_user_message.upper():
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text="LLM call was blocked by before_model_callback.")],
            )
        )
    return None  # proceed with the (optionally modified) request

my_llm_agent = LlmAgent(
    name="ModelCallbackAgent",
    model="gemini-2.0-flash",
    instruction="You are a helpful assistant.",
    before_model_callback=simple_before_model_modifier,
)
```

Modifying the request in-place before returning `None` is also valid — e.g. prefixing `llm_request.config.system_instruction`.

## Tool argument guardrail: `before_tool_callback`

`before_tool_callback(tool, args, tool_context)` can validate or rewrite arguments, or return a `dict` to short-circuit the tool entirely (e.g. to enforce a policy like "never allow writes to a specific resource").

## State management in callbacks

Reading/writing `callback_context.state['key']` (or `tool_context.state[...]`) inside a callback is tracked as `EventActions.state_delta` for the event the framework generates right after the callback runs — the same mechanism used by tools (see `sessions-and-state.md`).

## Memory auto-save via `after_agent_callback`

```python
async def auto_save_session_to_memory_callback(callback_context):
    await callback_context.add_session_to_memory()

agent = Agent(
    model="gemini-flash-latest",
    name="Generic_QA_Agent",
    tools=[PreloadMemoryTool()],
    after_agent_callback=auto_save_session_to_memory_callback,
)
```
