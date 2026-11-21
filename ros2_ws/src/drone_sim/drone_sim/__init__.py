"""Gazebo assets of Drone SITL (models, worlds) and where to find them."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory


def models_dir() -> Path:
    """Directory holding this project's Gazebo models."""
    return Path(get_package_share_directory("drone_sim")) / "models"


def worlds_dir() -> Path:
    """Directory holding this project's Gazebo worlds."""
    return Path(get_package_share_directory("drone_sim")) / "worlds"
