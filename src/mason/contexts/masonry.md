---
agent: MasonAgent

output_fields:
  bricks:
    description: >-
      List of the bricks in the design
  design_summary:
    description: >-
      As a 50-words standalone text to describe the your brick design.

user_prompts:
  initial: |
    Propose a new brick stacking design using NO MORE THAN 100 BRICKS, in the form of {form}, {techniques} and {geometric_attributes}.
    The brick has the default size of Width 0.2m x depth 0.1m x height 0.065m. Positive Z for UP, ground plane is set at Z=0.

    {reference_design}

    Call the validate_brick_design tool to test your design. Do not explain your code before calling the tool. Your first response must be a tool call. If the tool returns an error, analyze the error, fix the design, and call the tool again.
    If the user provide a reference design of their's, use the get_design_snapshot tool to get a visual of the reference design if needed.
    Return the final working design_summary as your answer.

  form: |
    A brick cylinder.
  techniques: |
    Use the techniques of harmonic stacking to enlarge the top of the column to create a column capital.
  geometric_attributes: |
    Utilize different orientation of the brick to have more variation on each stacking layer.
---

You are master brick mason. Based on a instruction of the user, your task is to come up with a brick stacking design and use the tool to validate if the design is stable. Focus on form, composition and the techniques. 