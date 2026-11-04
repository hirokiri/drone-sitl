"""Launch the simulator: Gazebo Jetty (via ros_gz_sim) and, later, PX4 SITL.

Usage:
    ros2 launch drone_bringup sim.launch.py
    ros2 launch drone_bringup sim.launch.py headless:=true world:=empty.sdf

PX4 SITL is not yet integrated: the container image does not ship PX4. This
launch file brings up Gazebo so the world/model pipeline can be developed; the
PX4 process and the uXRCE-DDS agent will be added here once the image has them
(see docs/specs/overview.md, section "Simulation").
"""

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution


def generate_launch_description() -> LaunchDescription:
    world = LaunchConfiguration("world")
    headless = LaunchConfiguration("headless")

    gz_sim_launch = PathJoinSubstitution(
        [get_package_share_directory("ros_gz_sim"), "launch", "gz_sim.launch.py"]
    )

    return LaunchDescription(
        [
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
            LogInfo(msg="PX4 SITL not yet integrated; launching Gazebo only."),
            # GUI + server
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(gz_sim_launch),
                launch_arguments={"gz_args": ["-r ", world]}.items(),
                condition=UnlessCondition(headless),
            ),
            # Server only
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(gz_sim_launch),
                launch_arguments={"gz_args": ["-r -s ", world]}.items(),
                condition=IfCondition(headless),
            ),
        ]
    )
