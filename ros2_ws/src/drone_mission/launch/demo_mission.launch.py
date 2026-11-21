"""Fly a scenario on the full stack and record it.

Usage:
    ros2 launch drone_mission demo_mission.launch.py
    ros2 launch drone_mission demo_mission.launch.py scenario:=/path/to/scenario.yaml
    ros2 launch drone_mission demo_mission.launch.py headless:=true run_dir:=runs/x

This is the entry point behind `make mission`. It brings up the stack via
drone_bringup/bringup.launch.py and selects a scenario file (default:
config/demo_mission.yaml). The one file drives the whole run, so it stays
reproducible from config (NFR5): the mission runner flies its plan over PX4
offboard control (arm, take off, the waypoints, land) and the GNSS injector,
part of the simulator bring-up, applies its GNSS-loss schedule. The flight
recorder logs PX4's estimate next to ground truth into `run_dir`. The launch
shuts down when the mission runner exits, so `make mission` ends with the
mission.
"""

from ament_index_python.packages import get_package_share_directory
from drone_bringup.sim_config import declare_sim_arguments, sim_argument_names
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
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
            # Pass-through simulator arguments (defaults: drone_bringup sim.yaml),
            # including the scenario, which here defaults to the demo.
            *declare_sim_arguments(scenario_default=default_scenario),
            DeclareLaunchArgument(
                "run_dir",
                default_value="runs/latest",
                description="Directory the flight log of this run is written to.",
            ),
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
            # --- Flight recorder (estimate vs ground truth) -----------------
            Node(
                package="drone_eval",
                executable="flight_recorder",
                parameters=[{"run_dir": LaunchConfiguration("run_dir")}],
                output="screen",
            ),
        ]
    )
