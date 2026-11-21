"""Accuracy metrics of a recorded flight (FR7): estimate vs ground truth."""

import math
from dataclasses import dataclass

from drone_eval.flight_log import Sample

# Samples used to line the two frames up: the vehicle is standing still on
# the ground with GNSS healthy, so estimate and truth describe the same spot.
ALIGNMENT_SAMPLES = 20


@dataclass(frozen=True)
class Errors:
    """Horizontal position error over a set of samples, in metres."""

    samples: int
    rmse_m: float
    max_m: float
    final_m: float


@dataclass(frozen=True)
class Window:
    """A stretch of the flight in which GNSS was not healthy."""

    mode: str
    start_s: float  # flight time
    end_s: float


def frame_offset(samples: list[Sample]) -> tuple[float, float, float]:
    """Constant (north, east, down) to add to estimates to get truth-frame.

    PX4's local frame starts wherever the estimator initialised; the
    simulator's world frame starts at the world origin.
    """
    head = samples[:ALIGNMENT_SAMPLES]
    if not head:
        raise ValueError("the flight log is empty")
    return (
        sum(s.truth_n - s.est_n for s in head) / len(head),
        sum(s.truth_e - s.est_e for s in head) / len(head),
        sum(s.truth_d - s.est_d for s in head) / len(head),
    )


def horizontal_errors(samples: list[Sample]) -> list[float]:
    """Horizontal distance between estimate and truth, per sample."""
    north, east, _ = frame_offset(samples)
    return [
        math.hypot(s.est_n + north - s.truth_n, s.est_e + east - s.truth_e)
        for s in samples
    ]


def summarise(errors: list[float]) -> Errors | None:
    if not errors:
        return None
    return Errors(
        samples=len(errors),
        rmse_m=math.sqrt(sum(e * e for e in errors) / len(errors)),
        max_m=max(errors),
        final_m=errors[-1],
    )


def in_flight(samples: list[Sample]) -> list[Sample]:
    return [s for s in samples if not math.isnan(s.flight_time_s)]


def loss_windows(samples: list[Sample]) -> list[Window]:
    """The in-flight periods during which GNSS was not passed on healthy.

    A loss the vehicle lands in ends, for this purpose, with the flight.
    """
    windows: list[Window] = []
    current: list[Sample] = []
    for sample in [*in_flight(samples), None]:
        mode = sample.gnss_mode if sample is not None else "healthy"
        if current and mode != current[0].gnss_mode:
            windows.append(
                Window(
                    current[0].gnss_mode,
                    current[0].flight_time_s,
                    current[-1].flight_time_s,
                )
            )
            current = []
        if sample is not None and mode != "healthy":
            current.append(sample)
    return windows


def phase_errors(samples: list[Sample]) -> dict[str, Errors | None]:
    """Error statistics in flight: overall, and before / during / after loss."""
    errors = horizontal_errors(samples)
    flying = [
        (s, e)
        for s, e in zip(samples, errors, strict=True)
        if not math.isnan(s.flight_time_s)
    ]
    windows = loss_windows(samples)
    result = {"flight": summarise([e for _, e in flying])}
    if windows:
        start, end = windows[0].start_s, windows[-1].end_s
        result["before_loss"] = summarise(
            [e for s, e in flying if s.flight_time_s < start]
        )
        result["during_loss"] = summarise(
            [e for s, e in flying if start <= s.flight_time_s <= end]
        )
        result["after_loss"] = summarise(
            [e for s, e in flying if s.flight_time_s > end]
        )
    return result


def first_flight_time(samples: list[Sample], condition) -> float | None:
    """Flight time of the first in-flight sample satisfying `condition`."""
    for sample in samples:
        if not math.isnan(sample.flight_time_s) and condition(sample):
            return sample.flight_time_s
    return None
