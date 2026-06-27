# Agents (`LlmAgent` / `Agent`)

`LlmAgent`, aliased as `Agent`, is the core LLM-powered agent class. Its behavior is non-deterministic — the model decides how to proceed, which tools to call, and what to output.

## Identity

- `name` (required): unique string identifier. Avoid reserved names like `user`. Crucial in multi-agent systems for routing/delegation.
- `description` (optional, recommended for multi-agent): summary used by *other* agents to decide whether to route a task here. Be specific (e.g. "Handles inquiries about current billing statements," not "Billing agent").
- `model` (required): string model identifier, e.g. `"gemini-flash-latest"`, or a `BaseLlm` instance (e.g. `LiteLlm(...)`, see `models.md`).

```python
capital_agent = LlmAgent(
    model="gemini-flash-latest",
    name="capital_agent",
    description="Answers user questions about the capital city of a given country.",
)
```

## Instructions

`instruction` is a string (or a function returning a string — an `InstructionProvider`) that sets the agent's task, persona, constraints, tool-usage guidance, and output format.

State templating: `{var}` inserts `session.state['var']`; `{artifact.var}` inserts the text content of artifact `var`. Append `?` to suppress the error when the key is missing: `{var?}`.

```python
capital_agent = LlmAgent(
    model="gemini-flash-latest",
    name="capital_agent",
    description="Answers user questions about the capital city of a given country.",
    instruction="""You are an agent that provides the capital city of a country.
When a user asks for the capital of a country:
1. Identify the country name from the user's query.
2. Use the `get_capital_city` tool to find the capital.
3. Respond clearly to the user, stating the capital city.
""",
)
```

For instructions that should apply to *every* agent in a multi-agent system, set `global_instruction` on the root agent.

## Tools

`tools` accepts: plain Python functions (auto-wrapped as `FunctionTool`), `BaseTool` subclass instances, or other agents wrapped in `AgentTool`. See `tools.md` for details.

```python
def get_capital_city(country: str) -> str:
    """Retrieves the capital city for a given country."""
    capitals = {"france": "Paris", "japan": "Tokyo", "canada": "Ottawa"}
    return capitals.get(country.lower(), f"Sorry, I don't know the capital of {country}.")

capital_agent = LlmAgent(
    model="gemini-flash-latest",
    name="capital_agent",
    tools=[get_capital_city],
)
```

## Fine-tuning model behavior: `generate_content_config`

Pass a `google.genai.types.GenerateContentConfig` to control `temperature`, `max_output_tokens`, `top_p`, `top_k`, safety settings, etc.

```python
from google.genai import types

agent = LlmAgent(
    model="gemini-flash-latest",
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
        max_output_tokens=250,
        safety_settings=[
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
            )
        ],
    ),
)
```

## Structured input/output: `input_schema`, `output_schema`, `output_key`

- `input_schema` (Pydantic `BaseModel`): if set, the message content passed to this agent *must* be a JSON string conforming to the schema.
- `output_schema` (Pydantic `BaseModel`): if set, the agent's final response *must* be a JSON string conforming to the schema.
- `output_key`: if set, the agent's final text response is automatically saved to `session.state[output_key]` — the standard way to pass results between agents/steps in a workflow.

**Using `output_schema` with `tools` in the same agent is only reliably supported by specific models (e.g. Gemini 3.0).** For other models, split into two agents: one with `tools` + `output_key`, a second with `output_schema` that formats the final result — `output_schema` generally disables tool use for that agent.

```python
from pydantic import BaseModel, Field

class CapitalOutput(BaseModel):
    capital: str = Field(description="The capital of the country.")

structured_capital_agent = LlmAgent(
    name="capital_formatter",
    model="gemini-flash-latest",
    instruction='Given a country, respond ONLY with JSON: {"capital": "capital_name"}',
    output_schema=CapitalOutput,
    output_key="found_capital",  # stored at session.state['found_capital']
)
```

## Managing context: `include_contents`

`include_contents` (default `'default'`) controls whether the agent receives prior conversation history. Set to `'none'` for stateless tasks that should only see the current instruction and current-turn input.

```python
stateless_agent = LlmAgent(model="gemini-flash-latest", include_contents="none")
```

## Planner

`planner` enables multi-step reasoning before execution.

- `BuiltInPlanner` leverages the model's native thinking feature (e.g. Gemini thinking budget):

```python
from google.adk.planners import BuiltInPlanner
from google.genai import types

agent = Agent(
    model="gemini-flash-latest",
    planner=BuiltInPlanner(
        thinking_config=types.ThinkingConfig(include_thoughts=True, thinking_budget=1024)
    ),
)
```

- `PlanReActPlanner` instructs the model to emit a structured `/*PLANNING*/ ... /*ACTION*/ /*REASONING*/ ... /*FINAL_ANSWER*/` format — useful for models without a native thinking mode:

```python
from google.adk.planners import PlanReActPlanner

agent = Agent(model="gemini-flash-latest", planner=PlanReActPlanner())
```

## Code execution

`code_executor` lets the agent execute code blocks found in the LLM's response.

```python
from google.adk.code_executors import BuiltInCodeExecutor

code_agent = LlmAgent(
    name="calculator_agent",
    model="gemini-2.0-flash",
    code_executor=BuiltInCodeExecutor(),
    instruction="Write and execute Python code to calculate the result. Return only the final numerical result.",
)
```
