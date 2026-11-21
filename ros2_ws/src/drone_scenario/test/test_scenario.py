"""Unit tests for scenario loading and validation."""

import copy
from pathlib import Path

import pytest
import yaml
from drone_scenario.scenario import ScenarioError, load_scenario, parse_scenario

SCENARIOS = Path(__file__).resolve().parents[2] / "drone_mission" / "config"
SCENARIO_FILE = SCENARIOS / "demo_mission.yaml"


def _demo() -> dict:
    return yaml.safe_load(SCENARIO_FILE.read_text())


def test_demo_scenario_loads():
    scenario = load_scenario(SCENARIO_FILE)
    assert scenario.name == "demo_gnss_loss"
    assert scenario.mission.waypoints_ned_m[0] == (50.0, 0.0, -20.0)


def test_legs_are_takeoff_then_waypoints():
    mission = load_scenario(SCENARIO_FILE).mission
    legs = mission.legs()
    assert legs[0] == (0.0, 0.0, -mission.takeoff_altitude_m)
    # The demo plan already ends over home: no extra return leg.
    assert legs[1:] == mission.waypoints_ned_m


def test_legs_return_over_home_before_landing():
    data = _demo()
    data["scenario"]["mission"]["waypoints_ned_m"] = [[30.0, 10.0, -15.0]]
    legs = parse_scenario(data).mission.legs()
    assert legs[-2:] == ((30.0, 10.0, -15.0), (0.0, 0.0, -15.0))


def test_legs_end_at_last_waypoint_without_land_at_home():
    data = _demo()
    data["scenario"]["mission"]["land_at_home"] = False
    mission = parse_scenario(data).mission
    assert mission.legs()[-1] == mission.waypoints_ned_m[-1]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("takeoff_altitude_m", 0),
        ("cruise_speed_m_s", -1.0),
        ("acceptance_radius_m", "big"),
        ("timeout_s", float("nan")),
        ("waypoints_ned_m", []),
        ("waypoints_ned_m", [[1.0, 2.0]]),
        ("waypoints_ned_m", [[1.0, 2.0, 5.0]]),  # below ground
        ("land_at_home", "yes"),
    ],
)
def test_rejects_unusable_values(key, value):
    data = _demo()
    data["scenario"]["mission"][key] = value
    with pytest.raises(ScenarioError):
        parse_scenario(data)


@pytest.mark.parametrize(
    "key", ["takeoff_altitude_m", "waypoints_ned_m", "cruise_speed_m_s", "timeout_s"]
)
def test_rejects_missing_keys(key):
    data = copy.deepcopy(_demo())
    del data["scenario"]["mission"][key]
    with pytest.raises(ScenarioError):
        parse_scenario(data)


@pytest.mark.parametrize("path", sorted(SCENARIOS.glob("*.yaml")), ids=lambda p: p.stem)
def test_every_shipped_scenario_loads(path):
    scenario = load_scenario(path)
    assert scenario.mission.waypoints_ned_m
    assert scenario.gnss_loss.mode in {"dropout", "degrade"}


def test_demo_scenario_drops_gnss_mid_flight():
    loss = load_scenario(SCENARIO_FILE).gnss_loss
    assert loss.enabled and loss.mode == "dropout"
    assert (loss.start_s, loss.end_s) == (30.0, 70.0)
    assert not load_scenario(SCENARIOS / "baseline_mission.yaml").gnss_loss.enabled


def test_scenario_without_gnss_loss_keeps_gnss():
    data = _demo()
    del data["scenario"]["gnss_loss"]
    assert not parse_scenario(data).gnss_loss.enabled


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("enabled", "yes"),
        ("start_s", -1.0),
        ("duration_s", 0),
        ("mode", "spoof"),
    ],
)
def test_rejects_unusable_gnss_loss(key, value):
    data = _demo()
    data["scenario"]["gnss_loss"][key] = value
    with pytest.raises(ScenarioError):
        parse_scenario(data)


def test_degrade_mode_needs_its_error_model():
    data = _demo()
    data["scenario"]["gnss_loss"]["mode"] = "degrade"
    del data["scenario"]["gnss_loss"]["degrade"]
    with pytest.raises(ScenarioError):
        parse_scenario(data)
    data["scenario"]["gnss_loss"]["degrade"] = {
        "noise_std_m": 0.0,
        "bias_std_m": 5.0,
        "bias_time_constant_s": 0.0,
    }
    with pytest.raises(ScenarioError):
        parse_scenario(data)
