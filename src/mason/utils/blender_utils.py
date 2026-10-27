import json
from dataclasses import dataclass

import bpy
from mathutils import Matrix, Vector


@dataclass
class BrickParams:
    mass: int = 2.5
    friction: float = 0.6
    restitution: float = 0.1
    use_margin: bool = True
    collision_margin: float = 0.001


class BlenderSimulation:
    def __init__(self, bricks_data, frame_start=1, frame_end=100, brick_params=BrickParams()):
        self.frame_start: int = frame_start
        self.frame_end: int = frame_end
        self.scene = bpy.context.scene
        self.bricks_data: list[dict] = bricks_data
        self.brick_params = brick_params

        # Clear the scene and set up the rigid body world
        self.clear_scene()
        self.setup_rigidbody_world()
        self.bricks = self.add_bricks()

        # Add a ground plane
        self.ground = self.add_ground()

    @staticmethod
    def clear_scene() -> None:
        # Use the data API: screen context members (context.object etc.) don't exist in background mode
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

    @staticmethod
    def add_rigidbody(obj: bpy.types.Object) -> None:
        # Operators need an active/selected object in context, which background mode doesn't provide
        with bpy.context.temp_override(object=obj, active_object=obj, selected_objects=[obj]):
            bpy.ops.rigidbody.object_add()

    def add_ground(self) -> bpy.types.Object:
        bpy.ops.mesh.primitive_plane_add(size=4.0, location=(0, 0, 0))
        ground = bpy.context.view_layer.objects.active
        ground.name = "Ground"
        self.add_rigidbody(ground)
        ground.rigid_body.type = "PASSIVE"  # collides but never moves
        ground.rigid_body.friction = 0.8
        return ground

    def setup_rigidbody_world(self, sub_steps=10, solver_iteration=20) -> bpy.types.RigidBodyWorld:
        if self.scene.rigidbody_world is None:
            bpy.ops.rigidbody.world_add()
        world = self.scene.rigidbody_world
        world.enabled = True
        world.substeps_per_frame = sub_steps  # more substeps = more stable contacts
        world.solver_iterations = solver_iteration
        world.point_cache.frame_start = self.frame_start
        world.point_cache.frame_end = self.frame_end
        self.scene.frame_start = self.frame_start
        self.scene.frame_end = self.frame_end
        return world

    def run_simulation(self, margin=0.01, log_every=10, verbose=False) -> dict:
        self.scene.frame_set(self.frame_start)

        depsgraph = bpy.context.evaluated_depsgraph_get()

        # Store initial world positions
        initial_positions = {
            b.name: b.evaluated_get(depsgraph).matrix_world.translation.copy() for b in self.bricks
        }

        result = {"success": True, "message": ""}

        for frame in range(self.frame_start, self.frame_end + 1):
            self.scene.frame_set(frame)
            depsgraph = bpy.context.evaluated_depsgraph_get()

            if frame % log_every == 0:
                for b in self.bricks:
                    pos = b.evaluated_get(depsgraph).matrix_world.translation
                    deviation = pos - initial_positions[b.name]

                    if deviation.length > margin:
                        result = {
                            "success": False,
                            "message": f"Brick {b.name} moved more than {margin}m in the direction of {deviation} at frame {frame}.",
                        }
                        break
                    elif verbose:
                        print(
                            f"Frame {frame:3d} | Brick {b.name} | Deviation: {deviation.length:.4f}m | Position: {pos}"
                        )

            if not result["success"]:
                break

        self.scene.frame_set(self.frame_start)
        return result

    def add_bricks(self) -> list[bpy.types.Object]:
        bricks = []
        for i, data in enumerate(self.bricks_data):
            location = data.get("position")
            rot = data.get("rotation")
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=location, rotation=rot)
            brick = bpy.context.view_layer.objects.active

            # Scale the mesh data directly to brick size so the collision shape matches the mesh
            brick.data.transform(
                Matrix.Diagonal(
                    (
                        0.2,  # width (cube is created with size=1.0)
                        0.1,  # depth
                        0.065,  # height
                        1.0,
                    )
                )
            )
            brick.data.update()

            # Add rigid body physics
            self.add_rigidbody(brick)
            rb = brick.rigid_body
            rb.type = "ACTIVE"  # moved by the simulation
            rb.collision_shape = "BOX"
            rb.mass = self.brick_params.mass  # kg, roughly a clay brick
            rb.friction = self.brick_params.friction
            rb.restitution = self.brick_params.restitution  # bounciness
            rb.use_margin = self.brick_params.use_margin
            rb.collision_margin = (
                self.brick_params.collision_margin
            )  # default 0.04 is too big for small objects
            brick.name = f"Brick_{i + 1}"
            bricks.append(brick)
        return bricks

    def get_snapshot(self, filepath, resolution=512, margin=1.2):
        scene = self.scene

        if not self.bricks:
            raise ValueError("No bricks to render")

        camera = None
        render = scene.render

        try:
            # Compute world-space bounding box of all bricks
            depsgraph = bpy.context.evaluated_depsgraph_get()
            points = []

            for brick in self.bricks:
                obj = brick.evaluated_get(depsgraph)

                for corner in obj.bound_box:
                    points.append(obj.matrix_world @ Vector(corner))

            min_corner = Vector(
                (
                    min(p.x for p in points),
                    min(p.y for p in points),
                    min(p.z for p in points),
                )
            )
            max_corner = Vector(
                (
                    max(p.x for p in points),
                    max(p.y for p in points),
                    max(p.z for p in points),
                )
            )

            center = (min_corner + max_corner) / 2

            # Create temporary camera
            camera_data = bpy.data.cameras.new("SnapshotCamera")
            camera = bpy.data.objects.new("SnapshotCamera", camera_data)
            scene.collection.objects.link(camera)

            direction = Vector((1, -1, 0.8)).normalized()
            camera.location = center + direction * 10
            camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()

            camera_data.type = "ORTHO"

            # Fit all bounding-box corners in the camera view
            camera_inv = camera.matrix_world.inverted()
            camera_points = [camera_inv @ p for p in points]

            width = max(p.x for p in camera_points) - min(p.x for p in camera_points)
            height = max(p.y for p in camera_points) - min(p.y for p in camera_points)

            camera_data.ortho_scale = max(width, height, 0.01) * margin

            scene.camera = camera

            # Fast Eevee rendering
            if bpy.app.version >= (5, 0, 0):
                render.engine = "BLENDER_EEVEE"
            elif bpy.app.version >= (4, 2, 0):
                render.engine = "BLENDER_EEVEE_NEXT"
            else:
                render.engine = "BLENDER_EEVEE"

            render.resolution_x = resolution
            render.resolution_y = resolution
            render.resolution_percentage = 100
            render.image_settings.file_format = "PNG"
            render.filepath = filepath

            bpy.ops.render.render(write_still=True)

            return filepath.read_bytes()

        finally:
            # Remove temporary camera
            if camera is not None:
                camera_data = camera.data
                bpy.data.objects.remove(camera, do_unlink=True)
                bpy.data.cameras.remove(camera_data)


if __name__ == "__main__":
    # Read example brick data from a JSON file and run the simulation
    with open("example_bricks.json", "r") as f:
        bricks_data = json.load(f)

    sim = BlenderSimulation(bricks_data, frame_start=1, frame_end=100)
    result = sim.run_simulation(log_every=10, verbose=True)
