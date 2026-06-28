---
name: adk
description: Use when building or modifying agents with Google's Agent Development Kit (google-adk Python package) — defining LlmAgent/Agent instances, function tools, multi-agent systems (sub_agents, AgentTool, SequentialAgent/ParallelAgent/LoopAgent), sessions and state, callbacks, structured output, streaming, or deploying ADK agents (Cloud Run, Agent Runtime, adk CLI). Applies to this repo's health_coach/ package which depends on google-adk>=2.3.0.
---

# Google ADK (Agent Development Kit) — Python

This skill covers the `google-adk` Python package used in `health_coach/`. ADK structures an agent application around a few primitives: **Agent** (LLM-powered or workflow-based), **Tool** (functions, other agents, MCP servers), **Session/State** (per-conversation memory), **Runner** (executes the agent loop and yields Events), and **Callbacks** (hooks into the execution lifecycle).

## Mental model

1. You define one or more `Agent` (alias for `LlmAgent`) instances. Each has a `name`, `model`, `instruction`, optional `description`, and optional `tools`.
2. A `root_agent` variable is the conventional entry point — `adk web`, `adk run`, and `adk deploy` all look for a module-level `root_agent`.
3. Tools are plain Python functions (auto-wrapped into `FunctionTool`), other `Agent` instances wrapped in `AgentTool`, or `MCPToolset` instances connecting to MCP servers.
4. A `Runner` ties an agent to a `SessionService` (and optionally `ArtifactService`/`MemoryService`) and drives execution: `runner.run_async(user_id=..., session_id=..., new_message=...)` yields a stream of `Event` objects.
5. State lives in `session.state` (a dict). Prefixes (`user:`, `app:`, `temp:`) control scope/persistence. Tools and callbacks read/write it via `ToolContext`/`CallbackContext` (now unified as `Context`).
6. Multi-agent systems compose agents via `sub_agents` (LLM-driven delegation/transfer), `AgentTool` (explicit agent-as-tool calls), or workflow agents (`SequentialAgent`, `ParallelAgent`, `LoopAgent`) for deterministic orchestration.

## Canonical patterns

### Minimal agent (matches this repo's `health_coach/agent.py` scaffold)

```python
from google.adk.agents import Agent

root_agent = Agent(
    name="health_coach_agent",
    model="gemini-2.5-flash",
    description="Friendly health and nutrition coaching assistant.",
    instruction=(
        "You are a helpful health coach. Use the available tools to log "
        "meals, weight, and look up nutrition info when the user asks."
    ),
    tools=[],  # function tools go here
)
```

### Function tool with proper type hints and docstring

ADK inspects the function signature (name, docstring, type hints, defaults) to build the tool schema sent to the LLM. Required params have no default; optional params have a default or `Optional[...] = None`. Return a `dict` with a `status` key — non-dict returns get wrapped as `{"result": ...}`.

```python
def log_weight(weight_kg: float, note: str | None = None) -> dict:
    """Logs the user's body weight for today.

    Args:
        weight_kg: The user's weight in kilograms.
        note: Optional free-text note about the measurement (e.g. "after workout").

    Returns:
        dict: status ("success" or "error") and a human-readable message.
    """
    # ... persist via health_coach/services ...
    return {"status": "success", "message": f"Logged {weight_kg} kg."}
```

### Tool reading/writing session state via `ToolContext`

```python
from google.adk.tools import ToolContext

def get_user_profile(tool_context: ToolContext) -> dict:
    """Retrieves the cached user profile from session state, if present."""
    profile = tool_context.state.get("user:profile")
    if not profile:
        return {"status": "error", "message": "No profile cached."}
    return {"status": "success", "profile": profile}
```

## Where to look for more detail

| Topic | File |
|---|---|
| Agent identity, instructions, output_schema/output_key, planners, code execution | `references/agents.md` |
| Function tools, ToolContext, long-running tools, AgentTool, MCP toolsets | `references/tools.md` |
| Session/State (`SessionService` impls, state prefixes), Memory (`MemoryService`) | `references/sessions-and-state.md` |
| Runner, Events, InvocationContext/Context object hierarchy | `references/runner-and-events.md` |
| sub_agents delegation, AgentTool, SequentialAgent/ParallelAgent/LoopAgent, custom BaseAgent | `references/multi-agent.md` |
| before/after agent/model/tool callbacks, guardrail patterns | `references/callbacks.md` |
| Gemini config, LiteLlm (Claude/OpenAI/Ollama/vLLM), model auth | `references/models.md` |
| Bidi-streaming (Live API), streaming tools | `references/streaming.md` |
| Artifacts (binary/file data, versioning, namespacing) | `references/artifacts.md` |
| `adk run`/`adk web` CLI, Cloud Run, Agent Runtime deployment | `references/deployment.md` |
| Agent Runtime IAM/identity (service account vs. per-agent identity, granting Firestore/Storage access to a deployed agent) | `references/agent-runtime-identity.md` |

Each reference file is self-contained with real, adapted-from-docs Python code. Read only the files relevant to the task at hand.
