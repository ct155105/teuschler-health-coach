# Streaming (Bidi-Streaming / Gemini Live API)

ADK's streaming support enables real-time, two-way (Bidi) communication over text/audio/video via the Gemini Live API. This is distinct from simple text token streaming — it supports mid-response interruption and simultaneous multimodal input/output.

Key architectural pieces: `LiveRequestQueue` (feeds live input — text, audio blobs, video frames — into the agent), the same `Agent`/`Runner` abstractions used for normal turns, and a streaming-capable model.

## Streaming Tools

A streaming tool lets a tool push intermediate results back to the agent while it runs, rather than returning once. Two kinds:

- **Simple** — takes ordinary (non-video/audio) input, yields intermediate string/object updates.
- **Video streaming** — takes a reserved `input_stream: LiveRequestQueue` parameter; ADK passes the live video/audio stream into the function.

Requirements: the tool must be an `async def` function whose return type is annotated `AsyncGenerator[YieldType, None]`.

```python
import asyncio
from typing import AsyncGenerator

from google.adk.agents import LiveRequestQueue
from google.adk.agents.llm_agent import Agent
from google.adk.tools.function_tool import FunctionTool

async def monitor_stock_price(stock_symbol: str) -> AsyncGenerator[str, None]:
    """Monitors the price for the given stock_symbol continuously, streaming results."""
    await asyncio.sleep(4)
    yield f"the price for {stock_symbol} is 300"
    await asyncio.sleep(4)
    yield f"the price for {stock_symbol} is 400"

async def monitor_video_stream(
    input_stream: LiveRequestQueue,
) -> AsyncGenerator[str, None]:
    """Monitor how many people are in the video stream."""
    while True:
        # drain input_stream, process the latest frame, yield on change
        ...

def stop_streaming(function_name: str):
    """Stop the streaming function named function_name.

    Args:
        function_name: The name of the streaming function to stop.
    """
    pass  # ADK calls this exact function/signature to let the agent halt a streaming tool

root_agent = Agent(
    model="gemini-flash-latest",
    name="video_streaming_agent",
    instruction="""You are a monitoring agent. Use monitor_video_stream for video monitoring
    and monitor_stock_price for stock monitoring. Don't be too talkative.""",
    tools=[monitor_video_stream, monitor_stock_price, FunctionTool(stop_streaming)],
)
```

Streaming tools are only supported via ADK's Gemini Live API integration (not standard turn-based `run_async`).

## Bidi-streaming characteristics

- **Two-way communication** — continuous exchange without waiting for a complete response; the model detects end-of-speech via voice activity detection or explicit signals.
- **Responsive interruption** — the user can interrupt the agent mid-response; the agent stops and addresses the new input immediately.
- **True multimodal** — text, audio, and video can be processed simultaneously over a single connection.

## Running a streaming agent locally

`adk web` supports voice/video streaming in its dev UI for quick manual testing. For a custom app, build on `LiveRequestQueue` + `Runner` directly (e.g. behind a FastAPI WebSocket endpoint) — see the official `bidi-demo` sample for a complete reference implementation (WebSocket transport, concurrent upstream/downstream tasks, text/audio output negotiation).

Supported voice/video models are limited to specific Gemini Live-capable model versions — check current docs for the latest supported list before picking a model string.
