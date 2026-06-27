# Artifacts

Artifacts are named, versioned **binary** data (images, PDFs, audio, etc.) associated with a session or a user, distinct from `session.state` which is for small serializable values. Represented as `google.genai.types.Part` with `inline_data` (a `Blob` of `data: bytes` + `mime_type: str`).

```python
import google.genai.types as types

image_bytes = b"\x89PNG\r\n\x1a\n..."
image_artifact = types.Part(inline_data=types.Blob(mime_type="image/png", data=image_bytes))
# Convenience constructor (equivalent):
image_artifact = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
```

## Why artifacts instead of state

- Binary/non-textual data (images, audio, PDFs, spreadsheets).
- Large blobs that shouldn't clutter session state.
- User file uploads/downloads.
- Sharing tool/agent outputs (e.g. a generated chart or report) across steps or sessions.
- Caching expensive-to-generate binary outputs.

## Configuring the `ArtifactService`

Required before any `save_artifact`/`load_artifact`/`list_artifacts` call on a context object — otherwise those calls raise `ValueError`.

```python
from google.adk.runners import Runner
from google.adk.artifacts import InMemoryArtifactService  # or GcsArtifactService
from google.adk.agents import LlmAgent
from google.adk.sessions import InMemorySessionService

agent = LlmAgent(name="artifact_user_agent", model="gemini-flash-latest")
artifact_service = InMemoryArtifactService()

runner = Runner(
    agent=agent,
    app_name="my_artifact_app",
    session_service=InMemorySessionService(),
    artifact_service=artifact_service,
)
```

`GcsArtifactService` persists to Google Cloud Storage instead.

## Versioning and namespacing

- `save_artifact` returns the new integer version (auto-incrementing per filename+scope, starting at 0).
- `load_artifact(filename)` loads the latest version by default; pass `version=N` for a specific one.
- `list_versions` (on the service) lists all version numbers for a filename.
- **Session scope (default):** plain filename, e.g. `"summary.txt"` — tied to `app_name` + `user_id` + `session_id`.
- **User scope:** prefix with `"user:"`, e.g. `"user:settings.json"` — tied to `app_name` + `user_id`, accessible from any of that user's sessions.

```python
session_report_filename = "summary.txt"        # session-scoped
user_config_filename = "user:settings.json"     # user-scoped, cross-session
```

## Interacting via context objects

`CallbackContext`/`ToolContext` (unified `Context`) expose `save_artifact(filename, part)`, `load_artifact(filename, version=None)`, and `list_artifacts()` — these abstract over whatever `ArtifactService` was configured on the `Runner`.
