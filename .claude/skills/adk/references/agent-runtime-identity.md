# Agent Runtime identity (IAM for deployed agents)

Not to be confused with an `Agent`'s `name` (see `agents.md`) — this is about how a **deployed Agent Runtime instance authenticates to other Google Cloud APIs** (Firestore, Cloud Storage, etc.) at runtime.

## Two modes

### 1. Default: shared service agent (no extra config)

Unless you explicitly opt in to agent identity, every Agent Runtime instance in a project authenticates as the same shared service account:

```text
service-{PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com
```

This account starts with only `roles/aiplatform.reasoningEngineServiceAgent` — **no Firestore/Storage access by default**. Your deployed agent's own code (e.g. `firebase_admin`/`google-cloud-firestore` calls) authenticates via Application Default Credentials, which resolve to this service account inside the container. To let your agent's code call Firestore/Storage, grant this service account project-level IAM roles directly:

```bash
PROJECT_NUMBER=123456789
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com" \
  --role="roles/datastore.user" \
  --condition=None

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin" \
  --condition=None
```

**This grants every Agent Runtime instance in the project the same access** — there's no per-agent scoping with this mode, since the service account is shared.

⚠️ IAM bindings can take roughly 1–2 minutes to propagate. A `403 Missing or insufficient permissions` error right after granting a role is often just propagation lag, not a real misconfiguration — retry the same request after a short wait before assuming the grant didn't work or that something else (like agent identity) is needed.

### 2. Opt-in: per-agent identity (`identity_type=AGENT_IDENTITY`)

For tighter scoping — e.g. multiple agents in one project that shouldn't share Firestore/Storage access — Agent Runtime supports a distinct identity *per agent instance* instead of the shared service account:

```python
remote_app = client.agent_engines.create(
    config={"identity_type": types.IdentityType.AGENT_IDENTITY},
    # ... agent config
)
```

The resulting principal identifier has this shape (not a normal service account email):

```text
principal://agents.global.org-{ORGANIZATION_ID}.system.id.goog/resources/aiplatform/projects/{PROJECT_NUMBER}/locations/{LOCATION}/reasoningEngines/{AGENT_ENGINE_ID}
```

Grant IAM roles to that principal the same way as any member:

```bash
gcloud {RESOURCE_TYPE} add-iam-policy-binding {RESOURCE_ID} \
  --member="principal://agents.global.org-{ORGANIZATION_ID}.system.id.goog/resources/aiplatform/projects/{PROJECT_NUMBER}/locations/{LOCATION}/reasoningEngines/{AGENT_ENGINE_ID}" \
  --role="{ROLE_NAME}"
```

Agents created this way automatically get baseline roles (`roles/aiplatform.agentContextEditor`, `roles/aiplatform.agentDefaultAccess`) and authenticate via Application Default Credentials the same way — `identity_type=AGENT_IDENTITY` just changes *which* principal ADC resolves to. The agent is secured with Context-Aware Access (mTLS-bound credentials usable only from the agent's own trusted runtime).

## Which mode does `teuschler-health-coach` use?

The default shared service agent — `health_coach` was deployed via `adk deploy agent_engine` without setting `identity_type`, so its Firestore/Storage access comes from IAM roles granted directly to `service-{PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com` on the project. If a second agent gets deployed into the same project later and needs *different* Firestore/Storage permissions, that's the point at which per-agent identity (mode 2) becomes necessary — the shared service account can't be scoped per-agent.

## Reference

https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-identity
