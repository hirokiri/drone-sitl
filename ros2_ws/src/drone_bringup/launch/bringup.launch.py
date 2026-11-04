"""Bring up the full Drone SITL stack: simulator + perception + estimation.

Usage:
    ros2 launch drone_bringup bringup.launch.py
    ros2 launch drone_bringup bringup.launch.py headless:=true world:=empty.sdf

This is the single entry point behind `make run`, so the composition of the
stack grows in one place. Today only the simulator slice exists and is
included from sim.launch.py. The perception stack (perception_common,
visual_matcher) and the estimation side (PX4 SITL + uXRCE-DDS agent feeding
EKF2) are added here as their packages land — see docs/specs/overview.md,
sections "Architecture" and "Proposed repository layout".
"""

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution


def generate_launch_description() -> LaunchDescription:
    world = LaunchConfiguration("world")
    headless = LaunchConfiguration("headless")

    sim_launch = PathJoinSubstitution(
        [get_package_share_directory("drone_bringup"), "launch", "sim.launch.py"]
    )

    return LaunchDescription(
        [
            # Pass-through simulator arguments (defaults live in sim.launch.py).
            DeclareLaunchArgument(
                "world",
                default_value="empty.sdf",
                description="Gazebo world file (name resolvable by gz, or a path).",
            ),
            DeclareLaunchArgument(
                "headless",
                default_value="false",
                description="Run the Gazebo server only, without the GUI.",
            ),
            # --- Simulation -------------------------------------------------
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(sim_launch),
                launch_arguments={"world": world, "headless": headless}.items(),
            ),
            # --- Perception (Rust: perception_common, visual_matcher) -------
            LogInfo(msg="Perception stack not yet integrated (no packages yet)."),
            # --- Estimation (PX4 SITL + uXRCE-DDS agent -> EKF2) ------------
            LogInfo(msg="Estimation stack not yet integrated (PX4 SITL pending)."),
        ]
    )
