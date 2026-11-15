"""Bring up the full Drone SITL stack: simulator + perception + estimation.

Usage:
    ros2 launch drone_bringup bringup.launch.py
    ros2 launch drone_bringup bringup.launch.py headless:=true world:=default.sdf

This is the single entry point behind `make run`, so the composition of the
stack grows in one place. Today only the simulator slice exists (Gazebo, PX4
SITL and the uXRCE-DDS agent, included from sim.launch.py). The perception
stack (perception_common, visual_matcher) and the external-vision feed into
EKF2 are added here as their packages land — see docs/specs/overview.md,
sections "Components" and "Proposed repository layout".
"""

from ament_index_python.packages import get_package_share_directory
from drone_bringup.sim_config import declare_sim_arguments, sim_argument_names
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, LogInfo
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution


def generate_launch_description() -> LaunchDescription:
    sim_launch = PathJoinSubstitution(
        [get_package_share_directory("drone_bringup"), "launch", "sim.launch.py"]
    )

    return LaunchDescription(
        [
            # Pass-through simulator arguments (defaults: config/sim.yaml).
            *declare_sim_arguments(),
            # --- Simulation -------------------------------------------------
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(sim_launch),
                launch_arguments={
                    name: LaunchConfiguration(name) for name in sim_argument_names()
                }.items(),
            ),
            # --- Perception (Rust: perception_common, visual_matcher) -------
            LogInfo(msg="Perception stack not yet integrated (no packages yet)."),
            # --- Estimation (visual pose -> EKF2 external vision) -----------
            LogInfo(msg="Estimation stack not yet integrated (visual pose pending)."),
        ]
    )
