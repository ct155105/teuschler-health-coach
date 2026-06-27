# Sessions, State, and Memory

## `Session`

A `Session` (`google.adk.sessions.Session`) is the container for one conversation thread: `id`, `app_name`, `user_id`, `events` (chronological history), `state` (scratchpad dict), `last_update_time`.

```python
from google.adk.sessions import InMemorySessionService

session_service = InMemorySessionService()
session = await session_service.create_session(
    app_name="my_app",
    user_id="example_user",
    state={"initial_key": "initial_value"},
)
```

## `SessionService` implementations

- **`InMemorySessionService`** — no persistence, lost on restart. Best for dev/testing.

  ```python
  from google.adk.sessions import InMemorySessionService
  session_service = InMemorySessionService()
  ```

- **`DatabaseSessionService`** — persists to a relational DB via an async driver. SQLite requires `sqlite+aiosqlite`, not plain `sqlite`.

  ```python
  from google.adk.sessions import DatabaseSessionService
  db_url = "sqlite+aiosqlite:///./my_agent_data.db"
  session_service = DatabaseSessionService(db_url=db_url)
  ```

  Uses in-process locking plus row-level locking (`SELECT ... FOR UPDATE`) on PostgreSQL/MySQL/MariaDB to serialize concurrent `append_event` calls on the same session.

- **`VertexAiSessionService`** — backed by Agent Runtime on Google Cloud; requires `pip install google-adk[vertexai]`, GCS bucket, and a Reasoning Engine resource name used as `app_name`.

  ```python
  from google.adk.sessions import VertexAiSessionService
  session_service = VertexAiSessionService(project="PROJECT_ID", location="us-central1")
  ```

## Session lifecycle

1. `create_session` (new chat) or resume with an existing `session_id`.
2. `Runner` fetches the `Session` and gives the agent access to its `state`/`events`.
3. Agent processes input, possibly using `state`/`events` for context.
4. Agent produces a response (and state changes); `Runner` packages this as an `Event`.
5. `Runner` calls `session_service.append_event(session, event)` — persists the event and applies state deltas.
6. Repeat for next turn; call `session_service.delete_session(...)` when done.

## State: `session.state`

A dict of string keys to serializable values (strings, numbers, booleans, lists/dicts of those). **Never store non-serializable objects** (class instances, functions, connections) — store an identifier instead.

### Scope prefixes

| Prefix | Scope | Persists with `InMemory`? | Use case |
|---|---|---|---|
| (none) | current session only | No (lost on restart) | task progress, current-turn flags |
| `user:` | all sessions for this `user_id` within the app | No | user preferences, profile (`user:theme`) |
| `app:` | all users/sessions in the app | No | global config (`app:api_endpoint`) |
| `temp:` | current invocation only, discarded after | N/A — never persisted | passing data between tool calls in one turn |

```python
session.state["current_intent"] = "book_flight"          # session-scoped
session.state["user:preferred_language"] = "fr"           # user-scoped
session.state["app:global_discount_code"] = "SAVE10"      # app-scoped
session.state["temp:raw_api_response"] = {...}             # invocation-scoped
```

Sub-agents invoked via `SequentialAgent`/`ParallelAgent`/`LoopAgent` share the parent's `InvocationContext`, and therefore the same `temp:` state and invocation id.

### Templating state into instructions

```python
story_generator = LlmAgent(
    name="StoryGenerator",
    model="gemini-flash-latest",
    instruction="Write a short story about a cat, focusing on the theme: {topic}.",
)
# If session.state['topic'] == "friendship", the LLM receives:
# "Write a short story about a cat, focusing on the theme: friendship."
```

### Reading/writing state in tools and callbacks

Via `tool_context.state` / `callback_context.state` (both backed by the unified `Context` type in current ADK Python). Writes are tracked as `EventActions.state_delta` and applied by the `SessionService` when the event is appended.

```python
from google.adk.tools import ToolContext

def my_tool(tool_context: ToolContext, **kwargs):
    user_pref = tool_context.state.get("user_display_preference", "default_mode")
    api_endpoint = tool_context.state.get("app:api_endpoint")
```

## Rewind sessions (ADK Python v1.17.0+)

`runner.rewind_async(user_id=..., session_id=..., rewind_before_invocation_id=...)` reverts session-level state/events/artifacts to before a given invocation, while keeping the rewound requests in the log for audit. App/user-level state and artifacts are **not** restored, and external side effects from tools are not undone.

## Memory: `MemoryService` (long-term, cross-session)

`Session`/`state` is short-term memory for one conversation. `MemoryService` is a searchable long-term store across sessions.

| Feature | `InMemoryMemoryService` | `VertexAiMemoryBankService` | `VertexAiRagMemoryService` |
|---|---|---|---|
| Persistence | None | Yes (Agent Platform) | Yes (Knowledge Engine) |
| Search | Keyword matching | Semantic search (LLM-extracted memories) | Vector similarity |
| Setup | None | Agent Runtime instance | Knowledge Engine corpus |

Core operations: `add_session_to_memory(session)`, `add_events_to_memory(...)` (optional), `add_memory(...)` (optional), `search_memory(query)`.

```python
from google.adk.memory import InMemoryMemoryService
memory_service = InMemoryMemoryService()
```

```python
from google.adk.memory import VertexAiMemoryBankService
memory_service = VertexAiMemoryBankService(project="PROJECT_ID", location="LOCATION", agent_engine_id=agent_engine_id)
```

### End-to-end pattern: capture, ingest, recall

```python
from google.adk.agents import LlmAgent
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.tools import load_memory
from google.genai.types import Content, Part

session_service = InMemorySessionService()
memory_service = InMemoryMemoryService()  # share across runners

info_capture_agent = LlmAgent(model="gemini-flash-latest", name="InfoCaptureAgent",
                               instruction="Acknowledge the user's statement.")
memory_recall_agent = LlmAgent(model="gemini-flash-latest", name="MemoryRecallAgent",
                                instruction="Use 'load_memory' if the answer might be in past conversations.",
                                tools=[load_memory])

# Turn 1: capture, then ingest the completed session into memory
runner1 = Runner(agent=info_capture_agent, app_name="app", session_service=session_service, memory_service=memory_service)
# ... run turn ...
completed_session = await session_service.get_session(app_name="app", user_id="u", session_id="s1")
await memory_service.add_session_to_memory(completed_session)

# Turn 2 (new session): recall via the load_memory tool
runner2 = Runner(agent=memory_recall_agent, app_name="app", session_service=session_service, memory_service=memory_service)
```

### Searching memory inside a custom tool

```python
from google.adk.tools import ToolContext

async def search_past_conversations(query: str, tool_context: ToolContext) -> dict:
    response = await tool_context.search_memory(query)
    return {
        "results": [
            part.text
            for entry in response.memories
            for part in (entry.content.parts or [])
            if part.text
        ]
    }
```

### Auto-saving sessions to memory via callback

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

The framework wires exactly one memory service per `adk web`/`adk api_server` instance (`--memory_service_uri`). To use a second knowledge base alongside it, instantiate a second `BaseMemoryService` directly inside a custom tool.
