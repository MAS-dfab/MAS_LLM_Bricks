import os

import logfire
from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider

load_dotenv(override=True)

if __name__ == "__main__":
    try:
        logfire.configure(token=os.getenv("LOGFIRE_TOKEN"))
        logfire.instrument_openai()
        print("Logfire configured successfully.")
    except Exception as e:
        print(f"Failed to configure Logfire: {e}")

    try:
        model = OpenAIResponsesModel(
            "gpt-6-luna",
            provider=OpenAIProvider(api_key=os.getenv("OPENAI_API_KEY")),
            settings=OpenAIResponsesModelSettings(openai_reasoning_effort="none"),
        )

        agent = Agent(
            model=model,
            output_type=str,
        )

        print("\n" + agent.run_sync("Tell me about Digital building technology ETH Zurich").output)
    except Exception as e:
        print(f"Failed to initialize OpenAI model: {e}")
