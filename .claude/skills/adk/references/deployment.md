# Deployment

## Local development: `adk run` / `adk web`

```bash
adk run my_agent        # interactive CLI
adk web --port 8000     # dev web UI with chat interface, run from the parent dir of my_agent/
```

`adk web` is for **development/debugging only** — not a production deployment target. Run it from the parent directory containing your agent package (e.g. if the agent is `agents/my_agent/`, run `adk web` from `agents/`).

`adk create my_agent` scaffolds a new agent project:

```text
my_agent/
    agent.py      # must define `root_agent`
    .env          # API keys / project IDs
    __init__.py
```

The required convention for any deployment path: the agent module defines a `root_agent` variable, and `__init__.py` contains `from . import agent`.

## Deployment targets

- **Agent Runtime** (Agent Platform on Google Cloud, formerly "Agent Engine"/Vertex AI Reasoning Engine) — fully managed, auto-scaling, purpose-built for ADK-style agents. This repo (`teuschler-health-coach`) targets this.
- **Cloud Run** — managed, container-based, auto-scaling general compute.
- **GKE** — for more control or when running self-hosted/open models.
- **Any container runtime** (Docker/Podman, offline/disconnected) — package manually and run anywhere.

## Agent Runtime

Agent Runtime is a paid service (free tier available) — see the [pricing page](https://cloud.google.com/vertex-ai/pricing#vertex-ai-agent-engine).

### Critical: what actually gets deployed (Python)

`adk deploy agent_engine` uploads **only your agent code and its declared dependencies** — for Python, this explicitly *excludes* the ADK API server and ADK web UI libraries; Agent Runtime provides those itself. Practically this means:

- Your deployed package is just `agent.py` (defining `root_agent`) + `__init__.py` (`from . import agent`) + `.env` — the same minimal shape `adk web`/`adk run` already use locally.
- **Any custom `Runner`/`SessionService`/`MemoryService` wiring you write locally (e.g. a `runtime.py`) does NOT ship to or run on Agent Runtime.** Once deployed, the platform wraps `root_agent` itself and serves it through its own managed `VertexAiSessionService` — your local session/memory wiring code is dev/test-only scaffolding, not part of the production code path.
- Session lifecycle in production is driven by whoever *calls* the deployed agent (a client app, a backend proxy), via the Agent Platform SDK or REST: `async_create_session(user_id=...)` → server returns a session, then `async_stream_query(user_id, session_id, message)` to converse.

### Prerequisites

- A Google Cloud project with the **Agent Platform API** (`aiplatform.googleapis.com`) and **Cloud Resource Manager API** enabled.
- `gcloud auth login` then `gcloud auth application-default login`.
- **The machine running `adk deploy` needs the `vertexai` SDK installed locally** — this is separate from what gets bundled into the deployed container. Without it, the deploy command fails with `Deploy failed: No module named 'vertexai'`. Install it as a project dependency: `uv add "google-cloud-aiplatform[agent_engines]"` (or `pip install`). This is a local/dev-time dependency for invoking the deploy API, not something your `agent.py` needs to import.
- **Your deployed agent's own code needs separate IAM grants to call other GCP APIs** (Firestore, Storage, etc.) — `adk deploy`'s prerequisites only cover the *deploy operation itself*, not what the running agent can access. See `references/agent-runtime-identity.md` for the default shared-service-account model and how to grant it Firestore/Storage access.

### What actually gets bundled (verified against ADK 2.3.0's `cli_deploy.py`)

`adk deploy agent_engine <agent_dir>` does a `shutil.copytree` of the **entire agent directory as-is** — there's no automatic exclusion of `__pycache__/`, local `.adk/` session caches, etc. To exclude files, add an **`.ae_ignore`** file inside the agent directory using `.gitignore`-style glob patterns:

```text
# health_coach/.ae_ignore
.adk
__pycache__
*.pyc
```

**Dependencies** come from a `requirements.txt` *inside the agent directory* (e.g. `health_coach/requirements.txt`), **not** from the project's `pyproject.toml`/`uv.lock` and **not** from the deprecated `--requirements_file` flag. If this file doesn't exist, ADK silently creates one containing only `google-adk[a2a]==<version>` — any other runtime dependency (`firebase-admin`, etc.) would be missing from the deployed container. Create it yourself listing your actual top-level deps (transitive deps like `httpx`/`python-dotenv` get pulled in automatically via `google-adk`'s/`firebase-admin`'s own dependency trees — no need to list them):

```text
# health_coach/requirements.txt
firebase-admin>=7.4.0
google-adk[otel-gcp]>=2.3.0
```

The CLI then auto-appends `google-cloud-aiplatform[agent_engines]` and `google-adk[a2a]==<version>` to this file if not already present — you don't need to add those yourself.

⚠️ **If using `--otel_to_cloud`, you need the `[otel-gcp]` extra, not just bare `google-adk`.** Without it, the deployed container's startup logs show warnings like `telemetry enabled but proceeding without gRPC instrumentation, because google-adk[otel-gcp] has not been installed` and `Unable to import GoogleGenAiSdkInstrumentor - some telemetry will be disabled`. Generic spans still reach Cloud Trace, but the **Agent Platform Traces view in the Cloud Console specifically needs this extra's instrumentation/semantic attributes to parse spans into agent sessions, model calls, and tool executions** — without it, that view appears to not be working at all (e.g. still prompting you to "enable tracing" even after `--otel_to_cloud` is set), even though raw trace data is technically being recorded.

**`.env` is read and shipped as environment variables** on the deployed resource: ADK reads `<agent_dir>/.env` (or `--env_file`) and passes its key/values as `env_vars` to the created Agent Engine instance. `GOOGLE_CLOUD_LOCATION` in `.env` *does* pass through unchanged even when `--region` is also passed (they serve different purposes — `--region` is where the Reasoning Engine resource itself lives; `GOOGLE_CLOUD_LOCATION` is what your agent's own genai/Vertex client uses, e.g. `"global"` for Gemini's global endpoint). Everything else in `.env` passes through as-is. Don't put secrets here that you don't want stored as plain env vars on the resource.

⚠️ **`GOOGLE_CLOUD_PROJECT` is the one exception — it gets dropped entirely**, not passed through, whenever `--project` is set (verified: it's simply absent from the deployed resource's env vars, confirmed via `GET .../reasoningEngines/{id}`). The deployed container then gets an *ambient* `GOOGLE_CLOUD_PROJECT` injected by the platform itself — set to the numeric **project number**, not the project ID string. This silently breaks any of your own code that reads `os.environ["GOOGLE_CLOUD_PROJECT"]` expecting the project ID (e.g. `firebase_admin`/Firestore project resolution does NOT treat project number and project ID as interchangeable — using the number gives `404 The database (default) does not exist for project {number}` even though the database exists under the project ID).

`load_dotenv()` defaults to `override=False`, so it won't fix this either — it never overwrites an already-set env var, and the ambient `GOOGLE_CLOUD_PROJECT` is already set before your code runs. **Fix: use a separate env var name your own code controls** for anything that needs the actual project ID string (e.g. `FIRESTORE_PROJECT_ID` instead of reusing `GOOGLE_CLOUD_PROJECT`) rather than fighting the platform with `load_dotenv(..., override=True)` — that would also clobber other ambient platform env vars you might not want overridden.

### Deploy

```bash
PROJECT_ID=my-project-id
LOCATION_ID=us-central1   # see https://docs.cloud.google.com/agent-builder/locations#supported-regions-agent-engine

adk deploy agent_engine \
    --project=$PROJECT_ID \
    --region=$LOCATION_ID \
    --display_name="My First Agent" \
    path/to/my_agent
```

Successful output includes a `RESOURCE_ID` (numeric, e.g. `751619551677906944`) identifying the deployed reasoning engine — needed for all future interaction with this deployment:

```text
AgentEngine created. Resource name: projects/123456789/locations/us-central1/reasoningEngines/751619551677906944
```

### Interacting with a deployed agent

Query URL shape:
```text
https://{LOCATION_ID}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION_ID}/reasoningEngines/{RESOURCE_ID}:query
```

Create a session, then send messages, via REST:
```bash
curl -H "Authorization: Bearer $(gcloud auth print-access-token)" -H "Content-Type: application/json" \
  https://$LOCATION-aiplatform.googleapis.com/v1/projects/$PROJECT/locations/$LOCATION/reasoningEngines/$RESOURCE:query \
  -d '{"class_method": "async_create_session", "input": {"user_id": "u_123"}}'
# response includes a server-generated numeric session "id" — extract it

curl -H "Authorization: Bearer $(gcloud auth print-access-token)" -H "Content-Type: application/json" \
  "https://$LOCATION-aiplatform.googleapis.com/v1/projects/$PROJECT/locations/$LOCATION/reasoningEngines/$RESOURCE:streamQuery?alt=sse" \
  -d '{"class_method": "async_stream_query", "input": {"user_id": "u_123", "session_id": "<id from above>", "message": "..."}}'
```

Or via the Agent Platform Python SDK:
```python
remote_app = agent_engines.get("projects/.../reasoningEngines/751619551677906944")
remote_session = await remote_app.async_create_session(user_id="u_456")

async for event in remote_app.async_stream_query(
    user_id="u_456", session_id=remote_session["id"], message="...",
):
    print(event)
```

Multimodal (image) queries — pass a list of `types.Part`, and prefer a GCS URI over inline bytes:
```python
from google.genai import types

image_part = types.Part.from_uri(file_uri="gs://bucket/photo.jpg", mime_type="image/jpeg")
text_part = types.Part.from_text(text="What is in this image?")

async for event in remote_app.async_stream_query(
    user_id="u_456", session_id=remote_session["id"], message=[text_part, image_part],
):
    print(event)
```

Clean up a test deployment: `remote_app.delete(force=True)` (also deletes child sessions).

### ⚠️ Custom/deterministic session IDs are currently unreliable

The `VertexAiSessionService`/Agent Runtime session API accepts an optional custom `session_id` in its interface, but as of this writing there are open upstream bugs (`google/adk-python` issues #987 and #2166) where supplying a custom session ID fails server-side — only server-auto-generated IDs reliably work. **Do not design a "deterministic session ID" scheme (e.g. session_id = today's date) against the deployed Agent Runtime session service** — it may break. If you need to find/reuse "today's session for this user" in production, list the user's sessions and match by creation/update timestamp instead of relying on a chosen ID string.

### Accelerated path: Agents CLI (`agents-cli`)

For a more batteries-included setup (CI/CD, Terraform IaC, telemetry) instead of the manual `adk deploy agent_engine` path above:
```bash
agents-cli scaffold enhance --deployment-target agent_engine   # adds deployment scaffolding to your project
gcloud auth application-default login
gcloud config set project your-project-id
agents-cli deploy   # reads deployment_target from pyproject.toml
```
This restructures the project (adds `app/`, `.cloudbuild/`, `deployment/`, `Makefile`, etc.) — heavier-weight than the manual path; prefer the manual `adk deploy agent_engine` path unless you specifically need the CI/CD scaffolding.

## Cloud Run

### Prerequisites

```bash
export GOOGLE_CLOUD_PROJECT=your-project-id
export GOOGLE_CLOUD_LOCATION=us-central1
export GOOGLE_GENAI_USE_VERTEXAI=True
```

Required agent directory layout:

```text
capital_agent/
├── __init__.py     # contains: from . import agent
└── agent.py        # defines `root_agent`
```

A `requirements.txt` in the agent directory.

### `adk deploy cloud_run` (recommended)

```bash
adk deploy cloud_run \
  --project=$GOOGLE_CLOUD_PROJECT \
  --region=$GOOGLE_CLOUD_LOCATION \
  --service_name=$SERVICE_NAME \
  --app_name=$APP_NAME \
  --with_ui \
  $AGENT_PATH
```

Key options: `--service_name` (default `adk-default-service-name`), `--app_name` (default = agent dir name), `--agent_engine_id` (for managed session service via Agent Runtime), `--port` (default 8000), `--with_ui` (also deploy the dev web UI — omit for API-only). Pass raw `gcloud` flags after a `--` separator:

```bash
adk deploy cloud_run --project=$P --region=$R path/to/agent -- --no-allow-unauthenticated --min-instances=2
```

Cloud Build permission is required on the default compute service account:

```bash
gcloud projects add-iam-policy-binding [PROJECT_ID] \
  --member="serviceAccount:[PROJECT_NUMBER]-compute@developer.gserviceaccount.com" \
  --role="roles/cloudbuild.builds.builder"
```

### Manual `gcloud run deploy` with a custom FastAPI app

For embedding the agent inside a custom FastAPI app instead of using the ADK-managed entry point:

```text
your-project-directory/
├── capital_agent/
│   ├── __init__.py
│   └── agent.py
├── main.py
├── requirements.txt
└── Dockerfile
```

```python
# main.py
import os
import uvicorn
from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_SERVICE_URI = "sqlite+aiosqlite:///./sessions.db"  # async driver required
ALLOWED_ORIGINS = ["http://localhost", "http://localhost:8080", "*"]

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    session_service_uri=SESSION_SERVICE_URI,
    allow_origins=ALLOWED_ORIGINS,
    web=True,
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
```

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN adduser --disabled-password --gecos "" myuser && chown -R myuser:myuser /app
COPY . .
USER myuser
ENV PATH="/home/myuser/.local/bin:$PATH"
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
```

```bash
gcloud run deploy capital-agent-service \
  --source . \
  --region $GOOGLE_CLOUD_LOCATION \
  --project $GOOGLE_CLOUD_PROJECT \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT,GOOGLE_CLOUD_LOCATION=$GOOGLE_CLOUD_LOCATION,GOOGLE_GENAI_USE_VERTEXAI=$GOOGLE_GENAI_USE_VERTEXAI"
```

Multiple agents can be deployed in one Cloud Run service by giving each its own subfolder, each defining its own `root_agent`:

```text
your-project-directory/
├── capital_agent/agent.py
├── population_agent/agent.py
```

## Session database migration (DatabaseSessionService)

If using `DatabaseSessionService` and upgrading to ADK Python v1.22.0+, the schema moved from pickle-based (`v0`) to JSON-based (`v1`) serialization. Migrate with:

```bash
adk migrate session --source_db_url=sqlite:///source.db --dest_db_url=sqlite:///dest.db
```

Requires ADK Python v1.22.1+.
