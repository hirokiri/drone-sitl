"""Run a demo mission on the full stack, with a GNSS-loss scenario.

Usage:
    ros2 launch drone_mission demo_mission.launch.py
    ros2 launch drone_mission demo_mission.launch.py scenario:=/path/to/scenario.yaml
    ros2 launch drone_mission demo_mission.launch.py headless:=true

This is the entry point behind `make mission`. It brings up the stack via
drone_bringup/bringup.launch.py and selects a scenario file (default:
config/demo_mission.yaml). The mission runner node (arm, take off, fly the
configured plan over offboard control) and the GNSS-loss injector are not yet
implemented; this file is where they get added, parameterised from the
scenario file, so the mission stays reproducible from config (NFR5).
"""

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution


def generate_launch_description() -> LaunchDescription:
    scenario = LaunchConfiguration("scenario")
    world = LaunchConfiguration("world")
    headless = LaunchConfiguration("headless")

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
            # --- Full stack (sim + perception + estimation) -----------------
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(bringup_launch),
                launch_arguments={"world": world, "headless": headless}.items(),
            ),
            # --- Mission runner + GNSS-loss injector (not yet implemented) --
            LogInfo(msg=["Scenario file: ", scenario]),
            LogInfo(
                msg="Mission runner not yet implemented (offboard control pending)."
            ),
            LogInfo(
                msg="GNSS-loss injector not yet implemented (gnss_injector pending)."
            ),
        ]
    )
