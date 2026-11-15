"""Smoke tests for the sim launch file and the config it reads."""

import importlib.util
from pathlib import Path

from drone_bringup.sim_config import load_px4_params, load_sim_config
from launch import LaunchDescription

LAUNCH_FILE = Path(__file__).resolve().parents[1] / "launch" / "sim.launch.py"


def _load_launch_module():
    spec = importlib.util.spec_from_file_location("sim_launch", LAUNCH_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generate_launch_description():
    ld = _load_launch_module().generate_launch_description()
    assert isinstance(ld, LaunchDescription)
    assert ld.entities, "launch description should not be empty"


def test_declares_simulator_arguments_with_config_defaults():
    ld = _load_launch_module().generate_launch_description()
    defaults = {
        arg.name: arg.default_value[0].text
        for arg in ld.entities
        if arg.__class__.__name__ == "DeclareLaunchArgument"
    }
    assert defaults == load_sim_config()
    assert {"world", "headless", "model"} <= defaults.keys()


def test_sim_config_is_well_formed():
    config = load_sim_config()
    assert config["world"].endswith(".sdf")
    assert config["headless"] in {"true", "false"}
    assert config["model"].startswith("gz_")


def test_startup_script_applies_overrides_after_stock_startup():
    params = load_px4_params()
    assert params, "sim.yaml should define px4_params"
    lines = _load_launch_module()._startup_script(params).splitlines()
    stock = lines.index(". etc/init.d-posix/rcS")
    for name, value in params.items():
        assert lines.index(f"param set {name} {value}") > stock
