"""Simulation launch defaults, loaded from config/sim.yaml.

The launch files of this repo expose the same simulator arguments (world,
headless, model, airframe). They all take their defaults from here so the
values live in one config file instead of being repeated as literals in each
launch file. `scenario` rides along with them: it has no default in sim.yaml
(no scenario means GNSS stays healthy), but every launch file passes it down
to the simulator, where the GNSS-loss injector reads it.
"""

from pathlib import Path

import yaml
from ament_index_python.packages import get_package_share_directory
from launch.actions import DeclareLaunchArgument

_DESCRIPTIONS = {
    "world": "Gazebo world file (name resolvable by gz, or a path). "
    "The file stem must equal the world name inside it.",
    "headless": "Run the Gazebo server only, without the GUI.",
    "model": "Gazebo model PX4 spawns (drone_sim's or PX4's model directory).",
    "airframe": "PX4 airframe (SYS_AUTOSTART) flown on the model.",
}
SCENARIO_ARGUMENT = "scenario"


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


def declare_sim_arguments(scenario_default="") -> list[DeclareLaunchArgument]:
    """Declare the simulator launch arguments with defaults from sim.yaml.

    `scenario_default` is the scenario file used when none is given; empty
    means no scenario (GNSS stays healthy).
    """
    defaults = load_sim_config()
    return [
        *(
            DeclareLaunchArgument(
                name, default_value=defaults[name], description=_DESCRIPTIONS[name]
            )
            for name in _DESCRIPTIONS
        ),
        DeclareLaunchArgument(
            SCENARIO_ARGUMENT,
            default_value=scenario_default,
            description="Scenario YAML (mission plan, GNSS-loss schedule, seed).",
        ),
    ]


def sim_argument_names() -> list[str]:
    """Names of the simulator launch arguments, for pass-through includes."""
    return [*_DESCRIPTIONS, SCENARIO_ARGUMENT]
