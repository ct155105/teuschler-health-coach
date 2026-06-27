# Models: Gemini, LiteLlm (Claude/OpenAI), and others

## Gemini (default)

Pass a model name string directly, or a `Gemini` model object for advanced config (e.g. custom `base_url` for self-hosted/edge models).

```python
from google.adk.agents import LlmAgent

agent_gemini_flash = LlmAgent(
    model="gemini-flash-latest",  # latest stable Flash alias
    name="gemini_flash_agent",
    instruction="You are a fast and helpful Gemini assistant.",
)
```

`gemini-flash-latest` resolves to the newest Flash version via the Gemini API. If accessing Gemini through a regional Vertex endpoint, use an explicit version string instead (the `-latest` alias may not resolve there).

### Authentication

Via `.env` or environment variables:

```bash
# Gemini Developer API
GOOGLE_API_KEY="PASTE_YOUR_GEMINI_API_KEY_HERE"
```

Or, for Vertex AI / Agent Platform:

```bash
export GOOGLE_CLOUD_PROJECT=your-project-id
export GOOGLE_CLOUD_LOCATION=us-central1
export GOOGLE_GENAI_USE_VERTEXAI=True
```

### Generation config

```python
from google.genai import types

agent = LlmAgent(
    model="gemini-flash-latest",
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
        max_output_tokens=250,
    ),
)
```

## LiteLlm — Claude, OpenAI, and 100+ other providers

`LiteLlm` wraps the [LiteLLM](https://docs.litellm.ai/) library to give ADK access to non-Gemini models through a standardized interface. Install separately: `pip install litellm`.

```python
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

# OpenAI (requires OPENAI_API_KEY)
agent_openai = LlmAgent(
    model=LiteLlm(model="openai/gpt-4o"),
    name="openai_agent",
    instruction="You are a helpful assistant powered by GPT-4o.",
)

# Anthropic Claude, non-Vertex (requires ANTHROPIC_API_KEY)
agent_claude_direct = LlmAgent(
    model=LiteLlm(model="anthropic/claude-3-haiku-20240307"),
    name="claude_direct_agent",
    instruction="You are an assistant powered by Claude Haiku.",
)
```

Set provider API keys as environment variables before constructing the agent:

```bash
export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
export ANTHROPIC_API_KEY="YOUR_ANTHROPIC_API_KEY"
```

Security note: a LiteLLM supply-chain compromise was identified in versions 1.82.7/1.82.8 on PyPI. If using ADK Python with the `eval` or `extensions` extras, keep ADK and LiteLLM updated, and rotate credentials if you installed/upgraded during the affected window.

Windows users may hit `UnicodeDecodeError` from LiteLLM reading cached files with `cp1252` — set `PYTHONUTF8=1` to force UTF-8 I/O.

### Local/self-hosted models via LiteLlm

- **Ollama** and **vLLM**: configure `LiteLlm` to point at your local server's OpenAI-compatible endpoint.
- **LiteRT-LM** (edge/desktop): use the `Gemini` model class directly with a custom `base_url` pointing at the local LiteRT-LM server, not `LiteLlm`:

  ```python
  from google.adk.agents import Agent
  from google.adk.models import Gemini

  root_agent = Agent(
      model=Gemini(model="gemma3n-e2b", base_url="http://localhost:8001"),
      name="dice_agent",
      instruction="You roll dice and answer questions about the outcome of the dice rolls.",
  )
  ```

## Claude on Agent Platform (Vertex AI), without LiteLLM

For Claude models served through Google Cloud's Agent Platform (rather than direct Anthropic API access via LiteLLM), ADK provides a dedicated integration path — register a `Claude` model class once at startup, then reference the Agent-Platform-specific model name in the agent. See the ADK "Claude models for ADK agents" doc for the registration call and required Agent Platform setup; this is a distinct path from the `LiteLlm(model="anthropic/...")` direct-API approach above.

## Choosing between Gemini, LiteLlm+Claude/OpenAI

- Use plain Gemini model strings for the common case — zero extra dependencies, full feature parity (planners, code execution, built-in tools).
- Use `LiteLlm` when you specifically need Claude, GPT, or another non-Gemini model, or want to run against a self-hosted/local model server.
- `output_schema` + `tools` together in one request is only reliably supported by specific models (e.g. Gemini 3.0) — for other models/providers, split structured-output formatting into a separate downstream agent (see `agents.md`).
