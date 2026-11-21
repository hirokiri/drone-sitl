"""What the GNSS injector does to the receiver's output, as plain functions.

Kept free of ROS and Gazebo so the schedule and the error model can be unit
tested and stay deterministic: the same scenario and seed give the same
sequence of positions.
"""

import math
import random
from enum import Enum

from drone_scenario.scenario import GnssDegradation, GnssLoss

# WGS84 semi-major axis; enough for turning metres into degrees over the few
# hundred metres a scenario covers.
EARTH_RADIUS_M = 6378137.0


class GnssMode(Enum):
    HEALTHY = "healthy"  # receiver output passed on untouched
    DROPOUT = "dropout"  # nothing passed on
    DEGRADE = "degrade"  # passed on with a position error added


def mode_at(loss: GnssLoss | None, flight_time_s: float | None) -> GnssMode:
    """GNSS mode `flight_time_s` seconds after takeoff (None: not flying)."""
    if loss is None or not loss.enabled or flight_time_s is None:
        return GnssMode.HEALTHY
    if not loss.start_s <= flight_time_s < loss.end_s:
        return GnssMode.HEALTHY
    return GnssMode(loss.mode)


class PositionError:
    """Horizontal position error of a degraded receiver, in metres.

    Per axis: white noise plus a bias that wanders as a first-order
    Gauss-Markov process with the configured steady-state spread.
    """

    def __init__(self, config: GnssDegradation, seed: int) -> None:
        self._config = config
        self._rng = random.Random(seed)
        self._bias = [0.0, 0.0]

    def reset(self) -> None:
        """Start the next degraded period from a zero bias."""
        self._bias = [0.0, 0.0]

    def step(self, dt_s: float) -> tuple[float, float]:
        """Advance by `dt_s` and return the (north, east) error."""
        config = self._config
        decay = math.exp(-max(dt_s, 0.0) / config.bias_time_constant_s)
        drive = config.bias_std_m * math.sqrt(1.0 - decay * decay)
        error = []
        for axis in range(2):
            self._bias[axis] = self._bias[axis] * decay + self._rng.gauss(0.0, drive)
            error.append(self._bias[axis] + self._rng.gauss(0.0, config.noise_std_m))
        return error[0], error[1]


def offset_position(
    latitude_deg: float, longitude_deg: float, north_m: float, east_m: float
) -> tuple[float, float]:
    """Move a geodetic position by a small north/east offset in metres."""
    latitude = latitude_deg + math.degrees(north_m / EARTH_RADIUS_M)
    longitude = longitude_deg + math.degrees(
        east_m / (EARTH_RADIUS_M * math.cos(math.radians(latitude_deg)))
    )
    return latitude, longitude
