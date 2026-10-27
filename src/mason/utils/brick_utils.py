from pydantic import BaseModel, Field

BRICK_WIDTH = 0.2  # m
BRICK_HEIGHT = 0.065  # m
BRICK_DEPTH = 0.1  # m


class Objective(BaseModel):
    ref_input_dir: str | None = Field(
        default=None, description="The directory of the reference design."
    )
    output_dir: str | None = Field(
        default=None, description="The directory to save the output design."
    )
    design_summary: str | None = None
    bricks_design: dict = {}
    simulation_result: dict | None = None
    user_prompt: str | None = None
    validation: bool | None = None
    attempts: int = Field(default=0, description="The number of attempts made by the agent.")


class Brick(BaseModel):
    position: tuple[float, float, float] = Field(
        ...,
        description="The (x, y, z) center point of the brick in meters. The dimensions of the brick are 0.2m x 0.1m x 0.065m (in X x in Y x in Z). So the position needs to be set accordingly to ensure the brick is placed correctly and not overlapping.",
    )
    rotation: tuple[float, float, float] = Field(
        default=(0.0, 0.0, 0.0), description="The (x, y, z) rotation of the brick in radians."
    )


class BrickDesign(BaseModel):
    bricks: list[Brick] = Field(
        ..., description="A list of bricks in the design (maximum 150).", max_length=150
    )
    design_summary: str
