# teuschler-health-coach

A proactive, data-driven weight loss and nutrition coach built on [Google's Agent Development Kit (ADK)](https://google.github.io/adk-docs/), deployed to [Vertex AI Agent Runtime](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/overview).

The agent tracks meals (from text or photos), body weight, and daily macro targets in Firestore, looks up authoritative nutrition data from the USDA FoodData Central database, and remembers user preferences across sessions via ADK's Memory Bank.

## How it works

- **`health_coach/agent.py`** — defines `root_agent`, an ADK `Agent` running on Gemini, wired up with the tools below and an instruction set that governs onboarding, meal tracking, and weight-trend reasoning.
- **Native multimodal vision** — meal photos are sent as image parts directly in the conversation; the agent's own model identifies food items and estimates portions, no separate vision tool needed.
- **`lookup_nutrition_tool`** — grounds every meal in real USDA FoodData Central data (not guessed/hallucinated macros), with a per-user Firestore cache so repeat foods skip redundant API calls.
- **`get_user_profile_tool` / `set_user_profile_tool`** — onboarding and profile management (age, sex, height, goal); new users are asked for this info before any nutrition guidance is given.
- **`log_meal_tool` / `log_weight_tool` / `get_daily_summary_tool`** — the quantitative ledger: meals, weigh-ins, and daily macro targets/consumed/remaining totals, all in Firestore.
- **Memory Bank** (`PreloadMemoryTool` + an `after_agent_callback`) — qualitative state (preferences, recent supplement intake, etc.) persists across days, separate from the daily Firestore ledger.

### Data layout (Firestore)

```text
users/{user_id}                                  -> profile (age, sex, height_in, goal, ...)
users/{user_id}/daily_summaries/{date}           -> targets + running totals + ADK session_id
users/{user_id}/daily_summaries/{date}/meals/{id} -> logged meals
users/{user_id}/weight_entries/{date}            -> one weigh-in per day
users/{user_id}/saved_meals/{hash}               -> cached nutrition lookups for repeat foods
```

## Project layout

```text
health_coach/
├── agent.py              # root_agent definition (the ADK entry point)
├── config.py             # centralized env-var configuration
├── runtime.py            # local dev Runner + daily-session-keying logic
├── services/             # Firestore, Cloud Storage, USDA API clients (no ADK imports)
├── tools/                # thin ADK tool wrappers around services/
├── app_utils/            # agents-cli scaffold: A2A protocol, telemetry, session/artifact wiring
└── fast_api_app.py        # agents-cli scaffold: custom FastAPI app (A2A + ADK + console proxy)
```

## Setup

1. Install dependencies: `uv sync`
2. Copy `health_coach/.env` and set:

   | Variable | Required | Purpose |
   |---|---|---|
   | `GOOGLE_CLOUD_PROJECT` | Yes | Used for Vertex AI/Gemini model calls |
   | `GOOGLE_CLOUD_LOCATION` | Yes | Vertex AI region/endpoint (e.g. `global` for Gemini's global endpoint) |
   | `FIRESTORE_PROJECT_ID` | Yes | Project ID for Firestore/Storage (kept separate from `GOOGLE_CLOUD_PROJECT` — see comment in `config.py`) |
   | `USDA_API_KEY` | For nutrition lookups | Free key: https://fdc.nal.usda.gov/api-key-signup |
   | `GOOGLE_GENAI_USE_ENTERPRISE` | Depends on setup | Whether to use Vertex AI (Enterprise) vs. the Gemini Developer API |

3. Run locally: `adk web` (from the repo root) for the dev UI, or `adk run health_coach` for an interactive CLI.

## Deployment

This project has been deployed two different ways — both work, with different tradeoffs:

### Option A: `adk deploy agent_engine` (simpler)

```bash
adk deploy agent_engine \
    --project=$GOOGLE_CLOUD_PROJECT \
    --region=us-central1 \
    --display_name="Health Coach" \
    --otel_to_cloud \
    health_coach
```

Minimal footprint — just `health_coach/` gets bundled (per `health_coach/requirements.txt` and `.ae_ignore`). IAM roles (`roles/datastore.user`, `roles/storage.objectAdmin`, `roles/cloudtrace.agent`, `roles/logging.logWriter`) and Cloud Trace content capture need to be configured manually; see `.claude/skills/adk/references/deployment.md` and `agent-runtime-identity.md` for the full gotchas list we hit along the way.

### Option B: `agents-cli` (more automation, heavier footprint)

```bash
uv tool install google-agents-cli
agents-cli infra single-project --apply   # provisions a dedicated service account, IAM, and a full BigQuery prompt/response logging pipeline
agents-cli deploy \
    --update-env-vars "FIRESTORE_PROJECT_ID=...,GOOGLE_GENAI_USE_ENTERPRISE=True,USDA_API_KEY=...,GOOGLE_CLOUD_LOCATION=global"
```

Provisions a dedicated service account, IAM bindings, and an automatic GCS → Cloud Logging → BigQuery pipeline for full prompt/response logging (`deployment/terraform/`). Notably: it does **not** read `health_coach/.env` — app-specific env vars must be passed via `--update-env-vars`, and `GOOGLE_CLOUD_PROJECT` is a platform-reserved name that can't be set this way.

## Status

This branch (`try-agents-cli-deploy`) was used to evaluate the `agents-cli` deployment path against the simpler `adk deploy agent_engine` flow. Both are live and working as of this writing. See commit history and `.claude/skills/adk/references/deployment.md` for the full list of gotchas discovered along the way (project-ID resolution in deployed containers, IAM role requirements, OpenTelemetry content-capture configuration, and Terraform packaging pitfalls).
