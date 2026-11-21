"""Scenario files: the mission plan and its schedule, loaded from YAML.

A scenario is the single description of a run (NFR5): the flight plan, the
GNSS-loss schedule and the RNG seed. This module parses and validates all of
it, so every node reads the same file the same way: the mission runner flies
`mission`, the GNSS injector applies `gnss_loss`.
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


GNSS_LOSS_MODES = ("dropout", "degrade")


@dataclass(frozen=True)
class GnssDegradation:
    """Error added to the GNSS position in `degrade` mode (horizontal only).

    White noise plus a slowly wandering bias (first-order Gauss-Markov), each
    drawn independently for north and east.
    """

    noise_std_m: float
    bias_std_m: float
    bias_time_constant_s: float


@dataclass(frozen=True)
class GnssLoss:
    """When GNSS is taken away, in seconds after takeoff, and how."""

    enabled: bool
    start_s: float
    duration_s: float
    mode: str
    degrade: GnssDegradation

    @property
    def end_s(self) -> float:
        return self.start_s + self.duration_s


@dataclass(frozen=True)
class Scenario:
    name: str
    seed: int
    mission: MissionPlan
    gnss_loss: GnssLoss


def _number(section: dict, key: str, where: str, minimum: float | None) -> float:
    """A finite number; above `minimum` if given, else merely non-negative."""
    value = section[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScenarioError(f"{where}.{key} must be a number, got {value!r}")
    if not math.isfinite(value) or value < 0 or (minimum is not None and value <= 0):
        kind = "positive" if minimum is not None else "zero or more"
        raise ScenarioError(f"{where}.{key} must be {kind}, got {value!r}")
    return float(value)


def _positive(section: dict, key: str, where: str = "mission") -> float:
    return _number(section, key, where, minimum=0.0)


def _gnss_loss(raw) -> GnssLoss:
    """Parse `gnss_loss`; a scenario without the section never loses GNSS."""
    no_degradation = GnssDegradation(0.0, 0.0, 1.0)
    if raw is None:
        return GnssLoss(False, 0.0, 0.0, "dropout", no_degradation)
    if not isinstance(raw["enabled"], bool):
        raise ScenarioError("gnss_loss.enabled must be true or false")
    if raw["mode"] not in GNSS_LOSS_MODES:
        raise ScenarioError(
            f"gnss_loss.mode must be one of {GNSS_LOSS_MODES}, got {raw['mode']!r}"
        )
    degrade = raw.get("degrade")
    if raw["mode"] == "degrade" and degrade is None:
        raise ScenarioError(
            "gnss_loss.mode is degrade but gnss_loss.degrade is missing"
        )
    return GnssLoss(
        enabled=raw["enabled"],
        start_s=_number(raw, "start_s", "gnss_loss", minimum=None),
        duration_s=_positive(raw, "duration_s", "gnss_loss"),
        mode=raw["mode"],
        degrade=no_degradation
        if degrade is None
        else GnssDegradation(
            noise_std_m=_number(degrade, "noise_std_m", "gnss_loss.degrade", None),
            bias_std_m=_number(degrade, "bias_std_m", "gnss_loss.degrade", None),
            bias_time_constant_s=_positive(
                degrade, "bias_time_constant_s", "gnss_loss.degrade"
            ),
        ),
    )


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
            gnss_loss=_gnss_loss(scenario.get("gnss_loss")),
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
