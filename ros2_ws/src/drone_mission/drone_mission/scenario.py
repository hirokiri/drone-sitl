"""Scenario files: the mission plan and its schedule, loaded from YAML.

A scenario is the single description of a run (NFR5): the flight plan, the
GNSS-loss schedule and the RNG seed. This module parses and validates the
part the mission runner flies; the `gnss_loss` section is left to the
GNSS-loss injector (milestone M2).
"""

import math
from dataclasses import dataclass
from pathlib import Path

import yaml

# A position in PX4's local frame convention: north, east, down [m].
Ned = tuple[float, float, float]


class ScenarioError(ValueError):
    """The scenario file is missing a key or holds an unusable value."""


@dataclass(frozen=True)
class MissionPlan:
    """arm -> takeoff -> waypoints -> land, relative to the home position."""

    takeoff_altitude_m: float
    waypoints_ned_m: tuple[Ned, ...]
    land_at_home: bool
    cruise_speed_m_s: float
    acceptance_radius_m: float
    timeout_s: float

    def legs(self) -> tuple[Ned, ...]:
        """Targets to fly in order, relative to home, before landing."""
        legs = [(0.0, 0.0, -self.takeoff_altitude_m), *self.waypoints_ned_m]
        over_home = (0.0, 0.0, legs[-1][2])
        if self.land_at_home and legs[-1] != over_home:
            # Come back over home at the altitude of the last leg, so the
            # landing itself is a straight descent.
            legs.append(over_home)
        return tuple(legs)


@dataclass(frozen=True)
class Scenario:
    name: str
    seed: int
    mission: MissionPlan


def _positive(section: dict, key: str) -> float:
    value = section[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScenarioError(f"mission.{key} must be a number, got {value!r}")
    if not math.isfinite(value) or value <= 0:
        raise ScenarioError(f"mission.{key} must be positive, got {value!r}")
    return float(value)


def _waypoint(index: int, raw) -> Ned:
    if (
        not isinstance(raw, (list, tuple))
        or len(raw) != 3
        or not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
            for v in raw
        )
    ):
        raise ScenarioError(
            f"mission.waypoints_ned_m[{index}] must be [north, east, down] in "
            f"metres, got {raw!r}"
        )
    if raw[2] >= 0:
        raise ScenarioError(
            f"mission.waypoints_ned_m[{index}] is not above ground: `down` "
            f"must be negative, got {raw[2]!r}"
        )
    return (float(raw[0]), float(raw[1]), float(raw[2]))


def parse_scenario(data: dict) -> Scenario:
    """Validate the parsed YAML document and return the scenario."""
    try:
        scenario = data["scenario"]
        mission = scenario["mission"]
        waypoints = mission["waypoints_ned_m"]
        if not isinstance(waypoints, list) or not waypoints:
            raise ScenarioError("mission.waypoints_ned_m must be a non-empty list")
        if not isinstance(mission["land_at_home"], bool):
            raise ScenarioError("mission.land_at_home must be true or false")
        return Scenario(
            name=str(scenario["name"]),
            seed=int(scenario["seed"]),
            mission=MissionPlan(
                takeoff_altitude_m=_positive(mission, "takeoff_altitude_m"),
                waypoints_ned_m=tuple(
                    _waypoint(i, wp) for i, wp in enumerate(waypoints)
                ),
                land_at_home=mission["land_at_home"],
                cruise_speed_m_s=_positive(mission, "cruise_speed_m_s"),
                acceptance_radius_m=_positive(mission, "acceptance_radius_m"),
                timeout_s=_positive(mission, "timeout_s"),
            ),
        )
    except (KeyError, TypeError) as error:
        raise ScenarioError(f"scenario is missing or malformed: {error!r}") from error


def load_scenario(path: str | Path) -> Scenario:
    """Load and validate a scenario YAML file."""
    path = Path(path)
    try:
        return parse_scenario(yaml.safe_load(path.read_text()))
    except ScenarioError as error:
        raise ScenarioError(f"{path}: {error}") from error
