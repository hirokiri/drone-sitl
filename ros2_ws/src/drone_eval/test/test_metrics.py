"""Unit tests for the flight log and the accuracy metrics computed from it."""

import math

import pytest
from drone_eval.flight_log import LogWriter, Sample, enu_to_ned, read_log
from drone_eval.report import build_report, describe, plot

from drone_eval import metrics

NAN = math.nan
# PX4's local origin sits here in the simulator's frame.
ORIGIN = (3.0, -2.0, 0.5)


def _sample(i: int, error_n: float = 0.0, mode: str = "healthy", valid: int = 1):
    """Sample `i` of a flight north at 1 m per sample, airborne from i = 20."""
    truth = (float(max(i - 20, 0)), 0.0, -10.0 if i >= 20 else 0.0)
    return Sample(
        time_s=i * 0.1,
        flight_time_s=(i - 20) * 0.1 if i >= 20 else NAN,
        truth_n=truth[0],
        truth_e=truth[1],
        truth_d=truth[2],
        est_n=truth[0] - ORIGIN[0] + error_n,
        est_e=truth[1] - ORIGIN[1],
        est_d=truth[2] - ORIGIN[2],
        est_xy_valid=valid,
        est_eph=0.2,
        gnss_mode=mode,
        nav_state=14,
        armed=1,
    )


def _flight() -> list[Sample]:
    """Healthy to i = 60, dropout with growing error to i = 80, healthy after."""
    samples = []
    for i in range(100):
        lost = 60 <= i < 80
        samples.append(
            _sample(
                i,
                error_n=float(i - 59) if lost else 0.0,
                mode="dropout" if lost else "healthy",
                valid=0 if 70 <= i < 80 else 1,
            )
        )
    return samples


def test_enu_to_ned():
    assert enu_to_ned(1.0, 2.0, 3.0) == (2.0, 1.0, -3.0)


def test_log_round_trips(tmp_path):
    writer = LogWriter(tmp_path / "run")
    samples = _flight()
    for sample in samples:
        writer.write(sample)
    writer.close()
    read = read_log(tmp_path / "run")
    assert len(read) == len(samples)
    assert read[30].truth_n == samples[30].truth_n
    assert read[30].gnss_mode == "healthy" and read[65].gnss_mode == "dropout"
    assert math.isnan(read[0].flight_time_s)
    assert read[30].flight_time_s == pytest.approx(1.0)


def test_frame_offset_is_recovered_from_the_stationary_start():
    assert metrics.frame_offset(_flight()) == pytest.approx(ORIGIN)


def test_error_is_zero_while_the_estimate_tracks_truth():
    errors = metrics.horizontal_errors(_flight())
    assert max(errors[:60]) == pytest.approx(0.0, abs=1e-9)
    assert errors[79] == pytest.approx(20.0)


def test_loss_window_is_reported_in_flight_time():
    (window,) = metrics.loss_windows(_flight())
    assert window.mode == "dropout"
    assert window.start_s == pytest.approx(4.0)
    assert window.end_s == pytest.approx(5.9)


def test_loss_window_ends_with_the_flight_when_landing_in_it():
    samples = [s for s in _flight() if s.time_s < 7.0]
    (window,) = metrics.loss_windows(samples)
    assert window.end_s == pytest.approx(4.9)


def test_errors_are_split_around_the_loss():
    phases = metrics.phase_errors(_flight())
    assert phases["before_loss"].max_m == pytest.approx(0.0, abs=1e-9)
    assert phases["during_loss"].max_m == pytest.approx(20.0)
    assert phases["during_loss"].final_m == pytest.approx(20.0)
    assert phases["after_loss"].rmse_m == pytest.approx(0.0, abs=1e-9)
    assert phases["flight"].samples == 80


def test_healthy_flight_has_no_loss_phases():
    samples = [_sample(i) for i in range(50)]
    assert metrics.loss_windows(samples) == []
    assert set(metrics.phase_errors(samples)) == {"flight"}


def test_report_states_when_the_estimate_went_invalid(tmp_path):
    report = build_report(_flight())
    assert report["estimate_invalid_at_s"] == pytest.approx(5.0)
    assert report["gnss_loss"][0]["mode"] == "dropout"
    assert "position invalid 5.0 s" in describe(report)
    plot(_flight(), tmp_path / "report.png", title="test")
    assert (tmp_path / "report.png").stat().st_size > 0
