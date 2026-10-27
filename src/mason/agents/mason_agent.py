import json
import os
from copy import deepcopy
from datetime import datetime as dt
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai import Agent, BinaryContent, RunContext, ToolReturn
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

from mason.contexts import load_context
from mason.utils.blender_utils import BlenderSimulation
from mason.utils.brick_utils import BrickDesign, Objective

load_dotenv(override=True)

MODEL_NAME_DEFAULT = "gpt-6-sol"
OUTPUT_DIR_DEFAULT = Path(__file__).parents[3] / "output"
MAX_GH_TOOL_CALLS = 3


class AgentFailedError(Exception):
    """Raised when an agent fails to produce output."""


class MasonAgent:
    def __init__(self, model_name=MODEL_NAME_DEFAULT):
        self._context = load_context("masonry")
        self.model = OpenAIResponsesModel(
            model_name,
            provider=OpenAIProvider(api_key=os.getenv("OPENAI_API_KEY")),
            settings=OpenAIResponsesModelSettings(openai_reasoning_effort="low"),
        )

        self.agent = Agent(
            model=self.model,
            name="MasonAgent",
            output_type=str,
            deps_type=dict,
            instructions=self._context.system_prompt,
        )
        self.last_usage = None

        @self.agent.tool
        def get_design_snapshot(ctx: RunContext[dict]) -> ToolReturn:
            try:
                ref_input_dir = ctx.deps.get("ref_input_dir")
                if ref_input_dir is None or not Path(ref_input_dir).exists():
                    return ToolReturn(return_value="No reference design provided by user.")
                else:
                    with open(ref_input_dir, "r") as f:
                        bricks_data = json.load(f)
                    sim = BlenderSimulation(bricks_data=bricks_data)

                    snapshot_path = (
                        ctx.deps.get("output_dir") / f"snapshot_{dt.now().strftime('%H%M%S')}.png"
                    )
                    data = sim.get_snapshot(filepath=snapshot_path)

                    return ToolReturn(
                        return_value="Successfully generated snapshot of the reference design.",
                        content=[BinaryContent(data=data, media_type="image/png")],
                    )
            except Exception as e:
                return ToolReturn(return_value=f"Error generating snapshot: {e}")

        @self.agent.tool(retries=3)
        def validate_brick_design(ctx: RunContext[dict], design: BrickDesign) -> ToolReturn:
            output_dir = Path(ctx.deps.get("output_dir"))
            print(f"Validating design with {len(design.bricks)} bricks...")
            try:
                bricks = design.bricks
                bricks_data = [brick.model_dump() for brick in bricks]
                summary = design.design_summary

                # Validate the design
                sim = BlenderSimulation(bricks_data=bricks_data)
                result = sim.run_simulation(log_every=5, verbose=False, margin=0.05)

                # Update the context with the validation result
                ctx.deps["validation"] = result["success"]
                ctx.deps["attempts"] = ctx.deps.get("attempts", 0) + 1
                ctx.deps["bricks_design"][ctx.deps.get("attempts", 0) + 1] = bricks_data
                ctx.deps["design_summary"] = summary
                ctx.deps["simulation_result"] = result
                print(result)

                snapshot_path = output_dir / f"snapshot_{dt.now().strftime('%H%M%S')}.png"
                snapshot = sim.get_snapshot(filepath=str(snapshot_path), frame=result.get("frame"))

                if result["success"]:
                    return ToolReturn(
                        return_value="Reference design validated.",
                        content=[BinaryContent(data=snapshot, media_type="image/png")],
                    )
                else:
                    return ToolReturn(
                        return_value="Validation failed the design is not stable. Please check the design and try again.",
                        content=[BinaryContent(data=snapshot, media_type="image/png")],
                    )
            except Exception as e:
                print(f"Error during design validation: {e}")
                return f"Error during design validation: {e}"
            finally:
                # save the result to a json file in the output dir
                with open(output_dir / "objective.json", "w") as f:
                    json.dump(ctx.deps, f, indent=4)

    def run(self, objective: Objective) -> Objective:
        # copy the objective to avoid modifying the original
        objective = deepcopy(objective)

        # create new folder for the session with date and time
        output_dir = OUTPUT_DIR_DEFAULT / f"session_{dt.now().strftime('%m%d_%H%M%S')}"
        output_dir.mkdir(parents=True, exist_ok=True)
        objective.output_dir = str(output_dir)

        # save the objective to a json file in the output dir
        with open(output_dir / "objective.json", "w") as f:
            json.dump(objective.model_dump(), f, indent=4)

        # read the design input from the objective
        if objective.ref_input_dir:
            ref_input_dir = objective.ref_input_dir
            if not ref_input_dir.exists():
                raise FileNotFoundError(f"Design input file not found: {ref_input_dir}")
            with open(ref_input_dir, "r") as f:
                ref_design = json.load(f)
        else:
            ref_design = None

        # render the user prompt
        text = self._context.render_user_prompt(
            "initial",
            form=self._context.user_prompts.get("form"),
            techniques=self._context.user_prompts.get("techniques"),
            geometric_attributes=self._context.user_prompts.get("geometric_attributes"),
            reference_design=ref_design,
        )

        deps = objective.model_dump()

        # run the agent synchronously with the user prompt and the objective as deps
        result = self.agent.run_sync(
            user_prompt=text,
            deps=deps,
            usage_limits=UsageLimits(tool_calls_limit=MAX_GH_TOOL_CALLS),
        )
        print("Agent run completed")
