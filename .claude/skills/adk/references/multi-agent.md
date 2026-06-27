# Multi-Agent Systems

ADK composes agents through three mechanisms: **LLM-driven delegation** (`sub_agents` + transfer), **explicit invocation** (`AgentTool`), and **deterministic workflow agents** (`SequentialAgent`, `ParallelAgent`, `LoopAgent`). You can also write a fully custom orchestrator by subclassing `BaseAgent`.

## LLM-driven delegation via `sub_agents`

The parent agent's LLM decides, based on each sub-agent's `description`, whether to transfer control by emitting `FunctionCall(name='transfer_to_agent', args={'agent_name': '...'})`. The framework then routes execution to that sub-agent.

```python
from google.adk.agents import LlmAgent

booking_agent = LlmAgent(name="Booker", description="Handles flight and hotel bookings.")
info_agent = LlmAgent(name="Info", description="Provides general information and answers questions.")

coordinator = LlmAgent(
    name="Coordinator",
    model="gemini-flash-latest",
    instruction="You are an assistant. Delegate booking tasks to Booker and info requests to Info.",
    description="Main coordinator.",
    sub_agents=[booking_agent, info_agent],
)
# If coordinator receives "Book a flight", its LLM emits:
# FunctionCall(name='transfer_to_agent', args={'agent_name': 'Booker'})
```

The framework sets `sub_agent.parent_agent` automatically when agents are assigned via `sub_agents`.

## Explicit invocation via `AgentTool`

Wrap any `BaseAgent` in `AgentTool` and add it to a parent's `tools` list — the LLM calls it like any other function tool, the framework runs the target agent, captures its final response, propagates state/artifact changes back, and returns the response as the tool result.

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

image_tool = agent_tool.AgentTool(agent=ImageGeneratorAgent())

artist_agent = LlmAgent(
    name="Artist",
    model="gemini-flash-latest",
    instruction="Create a prompt and use the ImageGen tool to generate the image.",
    tools=[image_tool],
)
```

## Workflow agents (deterministic orchestration)

These don't use an LLM for control flow — they orchestrate `sub_agents` directly and deterministically. They are good when you need a predictable pipeline rather than LLM-driven routing.

### `SequentialAgent`

Runs sub-agents one after another, in order. A later step can read state set by an earlier step (commonly via `output_key`).

```python
from google.adk.agents import SequentialAgent

pipeline = SequentialAgent(name="CityInfo", sub_agents=[agent_A, agent_B])
# AgentA runs, saves "Paris" to state['capital_city'].
# AgentB runs, its instruction reads state['capital_city'] via {capital_city} templating.
```

### `ParallelAgent`

Runs sub-agents concurrently; a subsequent agent (often in a surrounding `SequentialAgent`) can read state set by each branch.

```python
from google.adk.agents import ParallelAgent

gatherer = ParallelAgent(name="InfoGatherer", sub_agents=[fetch_weather, fetch_news])
# fetch_weather and fetch_news run concurrently, saving to state['weather'] / state['news'].
```

### `LoopAgent`

Repeats its sub-agents in sequence until `max_iterations` is reached or any sub-agent's event sets `actions.escalate = True`.

```python
from google.adk.agents import LoopAgent, SequentialAgent

refinement_loop = LoopAgent(
    name="CriticReviserLoop",
    sub_agents=[critic, reviser],
    max_iterations=5,
)
root_agent = SequentialAgent(name="FullPipeline", sub_agents=[initial_writer, refinement_loop])
```

### Generator/Critic/StopChecker pattern

A common composition: a `LoopAgent` wrapping a critic and a reviser, where a custom `BaseAgent` (a "checker") inspects state after the critic runs and sets `actions.escalate = True` to break the loop once a quality bar is met (e.g. critic output equals a known "done" phrase).

```python
loop_agent = LoopAgent(name="CriticReviserLoop", sub_agents=[critic, reviser], max_iterations=2)
sequential_agent = SequentialAgent(name="GenerateRefinePipeline", sub_agents=[initial_writer, loop_agent])
```

## Custom orchestrator agents (`BaseAgent` subclass)

When you need conditional branching that workflow agents don't natively support (e.g. "regenerate if the tone check fails"), subclass `BaseAgent` directly and orchestrate sub-agents imperatively inside `_run_async_impl`.

```python
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from typing import AsyncGenerator

class StoryFlowAgent(BaseAgent):
    def __init__(self, name, writer, critic, reviser, tone_checker):
        super().__init__(name=name, sub_agents=[writer, critic, reviser, tone_checker])
        self.writer = writer
        self.critic = critic
        self.reviser = reviser
        self.tone_checker = tone_checker

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        async for event in self.writer.run_async(ctx):
            yield event
        # ... custom conditional logic reading ctx.session.state, calling other
        # sub_agents, regenerating if a tone check fails ...
```

Declaring sub-agents in `super().__init__(sub_agents=[...])` is required so the framework is aware of the hierarchy (`parent_agent` wiring, event branching).

## Common multi-agent design patterns

- **Coordinator/dispatcher** — root LLM agent routes to specialist sub-agents via `transfer_to_agent`.
- **Sequential pipeline** — `SequentialAgent` chaining validator → processor → reporter, each reading/writing state.
- **Parallel fan-out/gather** — `ParallelAgent` for concurrent fetches, followed by a synthesizer agent reading all branch outputs from state.
- **Hierarchical task decomposition** — low-level tool-like agents wrapped via `AgentTool` into mid-level agents, composed into a high-level agent.
- **Generate-and-review** — generator agent + reviewer agent, optionally inside a `LoopAgent` for iterative refinement.
- **Human-in-the-loop** — a `LongRunningFunctionTool` (see `tools.md`) that defers to an external approval system before the next step proceeds.
