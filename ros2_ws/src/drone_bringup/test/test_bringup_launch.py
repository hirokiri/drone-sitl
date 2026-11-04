"""Smoke test: the bringup launch file imports and produces a launch description."""

import importlib.util
from pathlib import Path

from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription

LAUNCH_FILE = Path(__file__).resolve().parents[1] / "launch" / "bringup.launch.py"


def _load_launch_module():
    spec = importlib.util.spec_from_file_location("bringup_launch", LAUNCH_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generate_launch_description():
    ld = _load_launch_module().generate_launch_description()
    assert isinstance(ld, LaunchDescription)
    assert ld.entities, "launch description should not be empty"


def test_declares_world_and_headless_arguments():
    ld = _load_launch_module().generate_launch_description()
    names = {
        arg.name
        for arg in ld.entities
        if arg.__class__.__name__ == "DeclareLaunchArgument"
    }
    assert {"world", "headless"} <= names


def test_includes_the_simulator():
    ld = _load_launch_module().generate_launch_description()
    assert any(isinstance(e, IncludeLaunchDescription) for e in ld.entities)
