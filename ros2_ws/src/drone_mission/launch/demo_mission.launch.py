"""Run a demo mission on the full stack, with a GNSS-loss scenario.

Usage:
    ros2 launch drone_mission demo_mission.launch.py
    ros2 launch drone_mission demo_mission.launch.py scenario:=/path/to/scenario.yaml
    ros2 launch drone_mission demo_mission.launch.py headless:=true

This is the entry point behind `make mission`. It brings up the stack via
drone_bringup/bringup.launch.py and selects a scenario file (default:
config/demo_mission.yaml), which the mission runner flies over PX4 offboard
control: arm, take off, the waypoints, land. The launch shuts down when the
mission runner exits, so `make mission` ends with the mission. The GNSS-loss
injector is not yet implemented; this file is where it gets added,
parameterised from the same scenario file, so the run stays reproducible
from config (NFR5).
"""

from ament_index_python.packages import get_package_share_directory
from drone_bringup.sim_config import declare_sim_arguments, sim_argument_names
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    LogInfo,
    Shutdown,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    scenario = LaunchConfiguration("scenario")

    default_scenario = PathJoinSubstitution(
        [get_package_share_directory("drone_mission"), "config", "demo_mission.yaml"]
    )
    bringup_launch = PathJoinSubstitution(
        [get_package_share_directory("drone_bringup"), "launch", "bringup.launch.py"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "scenario",
                default_value=default_scenario,
                description="Scenario YAML (mission plan, GNSS-loss schedule, seed).",
            ),
            # Pass-through simulator arguments (defaults: drone_bringup sim.yaml).
            *declare_sim_arguments(),
            # --- Full stack (sim + perception + estimation) -----------------
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(bringup_launch),
                launch_arguments={
                    name: LaunchConfiguration(name) for name in sim_argument_names()
                }.items(),
            ),
            # --- Mission runner (arm -> takeoff -> waypoints -> land) -------
            Node(
                package="drone_mission",
                executable="mission_runner",
                parameters=[{"scenario": scenario}],
                output="screen",
                # The mission is what this launch is for: end with it.
                on_exit=Shutdown(reason="mission runner exited"),
            ),
            # --- GNSS-loss injector (not yet implemented) -------------------
            LogInfo(
                msg="GNSS-loss injector not yet implemented (gnss_injector pending)."
            ),
        ]
    )
