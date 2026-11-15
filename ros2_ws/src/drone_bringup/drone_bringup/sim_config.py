"""Simulation launch defaults, loaded from config/sim.yaml.

The launch files of this repo expose the same simulator arguments (world,
headless, model). They all take their defaults from here so the values live in
one config file instead of being repeated as literals in each launch file.
"""

from pathlib import Path

import yaml
from ament_index_python.packages import get_package_share_directory
from launch.actions import DeclareLaunchArgument

_DESCRIPTIONS = {
    "world": "Gazebo world file (name resolvable by gz, or a path). "
    "The file stem must equal the world name inside it.",
    "headless": "Run the Gazebo server only, without the GUI.",
    "model": "PX4 SITL airframe / Gazebo model, as gz_<model>.",
}


def _load() -> tuple[Path, dict]:
    path = Path(get_package_share_directory("drone_bringup")) / "config" / "sim.yaml"
    return path, yaml.safe_load(path.read_text())


def load_px4_params() -> dict[str, str]:
    """Return the PX4 parameter overrides (name -> value) from sim.yaml."""
    path, config = _load()
    if "px4_params" not in config:
        raise KeyError(f"{path}: missing key 'px4_params'")
    return {name: str(value) for name, value in config["px4_params"].items()}


def load_sim_config() -> dict[str, str]:
    """Return the simulator defaults as launch-argument strings."""
    path, config = _load()
    missing = _DESCRIPTIONS.keys() - config.keys()
    if missing:
        raise KeyError(f"{path}: missing keys {sorted(missing)}")
    return {
        name: str(config[name]).lower()
        if isinstance(config[name], bool)
        else str(config[name])
        for name in _DESCRIPTIONS
    }


def declare_sim_arguments() -> list[DeclareLaunchArgument]:
    """Declare the simulator launch arguments with defaults from sim.yaml."""
    defaults = load_sim_config()
    return [
        DeclareLaunchArgument(
            name, default_value=defaults[name], description=_DESCRIPTIONS[name]
        )
        for name in _DESCRIPTIONS
    ]


def sim_argument_names() -> list[str]:
    """Names of the simulator launch arguments, for pass-through includes."""
    return list(_DESCRIPTIONS)
