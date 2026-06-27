# Tools

Three main flavors: **Function Tools** (plain Python functions, auto-wrapped as `FunctionTool`), **Long Running Function Tools**, and **Agents-as-a-Tool** (`AgentTool`). Also covered: `ToolContext`, and MCP toolsets for connecting to external MCP servers.

## Function Tools

Assigning a function to an agent's `tools` list auto-wraps it as a `FunctionTool`. ADK inspects the function's name, docstring, parameters, type hints, and defaults to generate the schema the LLM uses to decide when/how to call it.

### Required vs optional parameters

A parameter is **required** if it has a type hint but no default value. It is **optional** if it has a default value, or is typed `Optional[T]` / `T | None` (Python 3.10+) with a default of `None`.

```python
def get_weather(city: str, unit: str):
    """Retrieves the weather for a city in the specified unit.

    Args:
        city (str): The city name.
        unit (str): The temperature unit, either 'Celsius' or 'Fahrenheit'.
    """
    return {"status": "success", "report": f"Weather for {city} is sunny."}

def search_flights(destination: str, departure_date: str, flexible_days: int = 0):
    """Searches for flights.

    Args:
        destination (str): The destination city.
        departure_date (str): The desired departure date.
        flexible_days (int, optional): Number of flexible days for the search. Defaults to 0.
    """
    ...
```

`*args` and `**kwargs` are **ignored** by the framework when generating the schema — the LLM is not aware of them and cannot pass values into them. Only use explicitly named parameters.

### Return type

Prefer returning a `dict`. Non-dict return values are automatically wrapped as `{"result": value}`. Always include a `status` key (`"success"`, `"error"`, `"pending"`) and prefer descriptive string messages over numeric codes — the LLM, not code, interprets the result.

### Docstrings

The docstring **is** the tool description sent to the LLM. Explain purpose, parameter meaning, and return value clearly.

### Best practices

- Fewer parameters are better.
- Favor primitive types (`str`, `int`, `float`, `bool`) over custom classes.
- Use meaningful, descriptive function and parameter names (avoid `do_stuff()`).
- Design for async/parallel execution when tools may be called concurrently.

### Passing data between tools within one turn

Use the `temp:` state prefix — all tool calls within a single agent turn share the same `InvocationContext` and therefore the same `temp:` state, discarded after the invocation completes.

```python
from google.adk.tools import ToolContext

def get_user_profile(tool_context: ToolContext) -> dict:
    tool_context.state["temp:current_user_id"] = "user-123"
    return {"profile_status": "ID generated"}

def get_user_orders(tool_context: ToolContext) -> dict:
    user_id = tool_context.state.get("temp:current_user_id")
    if not user_id:
        return {"error": "User ID not found in state"}
    return {"orders": ["order123", "order456"]}
```

### Full example with Runner

```python
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

APP_NAME, USER_ID, SESSION_ID = "stock_app", "1234", "session1234"

def get_stock_price(symbol: str):
    """Retrieves the current stock price for a given symbol.

    Args:
        symbol (str): The stock symbol (e.g., "AAPL", "GOOG").

    Returns:
        float: The current stock price, or None if an error occurs.
    """
    ...

stock_price_agent = Agent(
    model="gemini-2.0-flash",
    name="stock_agent",
    instruction="You are an agent who retrieves stock prices.",
    description="Retrieves real-time stock prices given a ticker symbol or company name.",
    tools=[get_stock_price],
)

async def setup_session_and_runner():
    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID)
    runner = Runner(agent=stock_price_agent, app_name=APP_NAME, session_service=session_service)
    return session, runner

async def call_agent_async(query):
    content = types.Content(role="user", parts=[types.Part(text=query)])
    session, runner = await setup_session_and_runner()
    async for event in runner.run_async(user_id=USER_ID, session_id=SESSION_ID, new_message=content):
        if event.is_final_response():
            print("Agent Response: ", event.content.parts[0].text)
```

## `ToolContext`

Passed as `tool_context` to function-tool implementations and tool callbacks. Adds to `CallbackContext`:

- `state` — mutable dict-like session state (read/write).
- `request_credential(auth_config)` / `get_auth_response(auth_config)` — auth flows.
- `list_artifacts()` — discover artifacts in the session.
- `search_memory(query)` — query the configured `MemoryService`.
- `function_call_id` — identifies the LLM function call that triggered this tool execution.
- `actions` — direct access to `EventActions` for this step (state changes, auth requests, etc).
- `agent_name`, `invocation_id` — identity/tracing.

```python
from google.adk.tools import ToolContext
from typing import Dict, Any

def search_external_api(query: str, tool_context: ToolContext) -> Dict[str, Any]:
    api_key = tool_context.state.get("api_key")
    if not api_key:
        return {"status": "Auth Required"}
    return {"result": f"Data for {query} fetched."}
```

## Long Running Function Tools

A `LongRunningFunctionTool` (subclass of `FunctionTool`) is for operations that take significant time and shouldn't block the agent. The wrapped function starts the operation and optionally returns an initial result (e.g. an operation id); the agent run then pauses, and the client decides whether to wait or continue with an intermediate/final response on a later turn. Useful for human-in-the-loop approval flows. The long-running tool only *starts and manages* the task — implement the actual long task in a separate service.

## Agents-as-a-Tool (`AgentTool`)

Wrap any `BaseAgent` (including `LlmAgent`) so a parent agent can call it like a function tool — synchronous, explicit invocation distinct from LLM-driven `sub_agents` transfer (see `multi-agent.md`).

```python
from google.adk.agents import LlmAgent, BaseAgent
from google.adk.tools import agent_tool

class ImageGeneratorAgent(BaseAgent):
    name: str = "ImageGen"
    description: str = "Generates an image based on a prompt."
    async def _run_async_impl(self, ctx):
        prompt = ctx.session.state.get("image_prompt", "default prompt")
        image_bytes = b"..."
        yield Event(author=self.name, content=types.Content(
            parts=[types.Part.from_bytes(image_bytes, "image/png")]
        ))

image_agent = ImageGeneratorAgent()
image_tool = agent_tool.AgentTool(agent=image_agent)

artist_agent = LlmAgent(
    name="Artist",
    model="gemini-flash-latest",
    instruction="Create a prompt and use the ImageGen tool to generate the image.",
    tools=[image_tool],
)
```

## MCP Toolsets

`McpToolset` / `MCPToolset` connects to an MCP server (stdio subprocess or remote HTTP) and exposes its tools to the agent.

### Stdio (local subprocess) connection

```python
from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

root_agent = Agent(
    model="gemini-flash-latest",
    name="advertising_agent",
    instruction="You are an advertising agent...",
    tools=[
        McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command="npx",
                    args=["-y", "mcp-remote", "https://mcp.example.com/mcp"],
                ),
                timeout=30,
            ),
        )
    ],
)
```

### Streamable HTTP connection

```python
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams

ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"

root_agent = Agent(
    model="gemini-flash-latest",
    name="advertising_agent",
    tools=[
        McpToolset(
            connection_params=StreamableHTTPConnectionParams(
                url="https://mcp.example.com/mcp",
                headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
            ),
        )
    ],
)
```

This repo has `health_coach/services/mcp_client.py` reserved for this kind of integration.

## Built-in tools

ADK ships pre-built tools, e.g.:

- `PreloadMemoryTool` — always retrieves memory at the start of each turn (see `sessions-and-state.md`).
- `LoadMemoryTool` / `load_memory` — lets the agent decide when to query the memory service.

```python
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

agent = Agent(model="gemini-flash-latest", name="agent", tools=[PreloadMemoryTool()])
```

## Streaming tools (Live API only)

An `async` Python function typed to return `AsyncGenerator` can stream intermediate results back to the agent (e.g. monitoring a stock price or a video stream). Only supported with ADK's Gemini Live API streaming. See `streaming.md`.
