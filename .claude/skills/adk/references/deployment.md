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

- **Agent Runtime** (Agent Platform on Google Cloud) — fully managed, auto-scaling, purpose-built for ADK-style agents.
- **Cloud Run** — managed, container-based, auto-scaling general compute.
- **GKE** — for more control or when running self-hosted/open models.
- **Any container runtime** (Docker/Podman, offline/disconnected) — package manually and run anywhere.

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
