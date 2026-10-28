import os
from pathlib import Path

import logfire
from dotenv import load_dotenv

from mason.agents.mason_agent import MasonAgent
from mason.utils.brick_utils import Objective

INPUT_DIR = Path(__file__).parent / "input"
INPUT_DESIGN_FILE = INPUT_DIR / "brick_design_01.json"
load_dotenv(override=True)

if __name__ == "__main__":
    try:
        logfire.configure(token=os.getenv("LOGFIRE_TOKEN"))
        logfire.instrument_openai()
        print("Logfire configured successfully.")
    except Exception as e:
        print(f"Failed to configure Logfire: {e}")

    # create an objective
    if not INPUT_DESIGN_FILE.exists():
        ref = None
    else:
        ref = str(INPUT_DESIGN_FILE)
    objective = Objective(ref_input_dir=ref)

    # create an agent
    agent = MasonAgent()

    # run the agent with the objective
    try:
        result = agent.run(objective)
        print(f"Agent run completed: {result}")
    except Exception as e:
        print(f"Agent run failed: {e}")
