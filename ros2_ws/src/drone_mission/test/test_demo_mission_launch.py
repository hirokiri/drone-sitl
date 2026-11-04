"""Smoke test: the demo mission launch file imports and produces a launch description."""

import importlib.util
from pathlib import Path

import yaml
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription

PKG_DIR = Path(__file__).resolve().parents[1]
LAUNCH_FILE = PKG_DIR / "launch" / "demo_mission.launch.py"
SCENARIO_FILE = PKG_DIR / "config" / "demo_mission.yaml"


def _load_launch_module():
    spec = importlib.util.spec_from_file_location("demo_mission_launch", LAUNCH_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generate_launch_description():
    ld = _load_launch_module().generate_launch_description()
    assert isinstance(ld, LaunchDescription)
    assert ld.entities, "launch description should not be empty"


def test_declares_scenario_world_and_headless_arguments():
    ld = _load_launch_module().generate_launch_description()
    names = {
        arg.name
        for arg in ld.entities
        if arg.__class__.__name__ == "DeclareLaunchArgument"
    }
    assert {"scenario", "world", "headless"} <= names


def test_includes_the_bringup():
    ld = _load_launch_module().generate_launch_description()
    assert any(isinstance(e, IncludeLaunchDescription) for e in ld.entities)


def test_demo_scenario_is_well_formed():
    scenario = yaml.safe_load(SCENARIO_FILE.read_text())["scenario"]
    assert isinstance(scenario["seed"], int)
    assert scenario["mission"]["waypoints_ned_m"], "mission needs waypoints"
    assert all(len(wp) == 3 for wp in scenario["mission"]["waypoints_ned_m"])
    gnss = scenario["gnss_loss"]
    assert gnss["start_s"] >= 0 and gnss["duration_s"] > 0
    assert gnss["mode"] in {"dropout", "degrade"}
