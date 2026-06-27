from google.adk.agents import Agent


root_agent = Agent(
    name="weather_time_agent",
    model="gemini-2.5-flash",
    description=(
        "You are a friendly and helpful assistant."
    ),
    instruction=(
        "You are a helpful agent who can answer user questions about the time and weather in a city."
    ),
    # tools=[get_weather, get_current_time],
)