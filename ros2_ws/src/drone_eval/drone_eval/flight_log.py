"""The flight log: one CSV row per sample, estimate next to ground truth.

Shared by the recorder (writes it) and the report (reads it), and free of ROS
so both sides can be unit tested.

Positions are metres in a north-east-down frame. `truth_*` is the simulator's
exact pose, converted from Gazebo's east-north-up world frame. `est_*` is
PX4's own estimate (EKF2) in its local frame, whose origin is wherever the
estimator initialised. The two origins differ by a constant the report
removes; nothing here feeds back into the vehicle.
"""

import csv
import math
from dataclasses import asdict, dataclass, fields
from pathlib import Path

LOG_NAME = "flight.csv"
NAN = math.nan


@dataclass(frozen=True)
class Sample:
    time_s: float  # PX4 clock, seconds since the first sample
    flight_time_s: float  # seconds since takeoff; NaN on the ground
    truth_n: float
    truth_e: float
    truth_d: float
    est_n: float
    est_e: float
    est_d: float
    est_xy_valid: int  # PX4 considers its horizontal position usable
    est_eph: float  # PX4's own 1-sigma horizontal accuracy estimate [m]
    gnss_mode: str  # healthy | dropout | degrade (from the GNSS injector)
    nav_state: int  # PX4 navigation state (VehicleStatus.nav_state)
    armed: int


FIELDS = [f.name for f in fields(Sample)]
_TYPES = {f.name: f.type for f in fields(Sample)}


def enu_to_ned(east: float, north: float, up: float) -> tuple[float, float, float]:
    """Gazebo world position (ENU) as north-east-down."""
    return north, east, -up


class LogWriter:
    """Append samples to `<directory>/flight.csv`, flushed row by row."""

    def __init__(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / LOG_NAME
        self._file = self.path.open("w", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=FIELDS)
        self._writer.writeheader()

    def write(self, sample: Sample) -> None:
        row = asdict(sample)
        for name, value in row.items():
            if isinstance(value, float):
                row[name] = f"{value:.4f}"
        self._writer.writerow(row)
        # The recorder is stopped by a signal when the launch ends; keep what
        # is on disk complete at all times.
        self._file.flush()

    def close(self) -> None:
        self._file.close()


def read_log(path: Path) -> list[Sample]:
    """Read a flight log; `path` is the CSV file or the run directory."""
    if path.is_dir():
        path = path / LOG_NAME
    with path.open(newline="") as file:
        return [
            Sample(**{name: _TYPES[name](row[name]) for name in FIELDS})
            for row in csv.DictReader(file)
        ]
