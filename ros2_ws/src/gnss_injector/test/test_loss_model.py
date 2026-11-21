"""Unit tests for the GNSS-loss schedule and the degraded-position error."""

import math
import statistics

import pytest
from drone_scenario.scenario import GnssDegradation, GnssLoss
from gnss_injector.loss_model import (
    GnssMode,
    PositionError,
    mode_at,
    offset_position,
)

DEGRADATION = GnssDegradation(
    noise_std_m=1.5, bias_std_m=8.0, bias_time_constant_s=20.0
)


def _loss(mode="dropout", enabled=True) -> GnssLoss:
    return GnssLoss(
        enabled, start_s=30.0, duration_s=40.0, mode=mode, degrade=DEGRADATION
    )


def test_gnss_is_lost_only_inside_the_window():
    loss = _loss()
    assert mode_at(loss, 29.9) is GnssMode.HEALTHY
    assert mode_at(loss, 30.0) is GnssMode.DROPOUT
    assert mode_at(loss, 69.9) is GnssMode.DROPOUT
    assert mode_at(loss, 70.0) is GnssMode.HEALTHY


def test_mode_follows_the_scenario():
    assert mode_at(_loss("degrade"), 40.0) is GnssMode.DEGRADE


def test_healthy_when_disabled_absent_or_on_the_ground():
    assert mode_at(_loss(enabled=False), 40.0) is GnssMode.HEALTHY
    assert mode_at(None, 40.0) is GnssMode.HEALTHY
    assert mode_at(_loss(), None) is GnssMode.HEALTHY


def test_position_error_is_reproducible_from_the_seed():
    a, b = PositionError(DEGRADATION, 42), PositionError(DEGRADATION, 42)
    assert [a.step(0.033) for _ in range(100)] == [b.step(0.033) for _ in range(100)]
    other = PositionError(DEGRADATION, 43)
    assert a.step(0.033) != other.step(0.033)


def test_position_error_has_the_configured_spread():
    error = PositionError(DEGRADATION, 1)
    # Sample far apart in time so the bias decorrelates between samples.
    north = [error.step(200.0)[0] for _ in range(4000)]
    expected = math.hypot(DEGRADATION.bias_std_m, DEGRADATION.noise_std_m)
    assert abs(statistics.fmean(north)) < 0.5
    assert statistics.pstdev(north) == pytest.approx(expected, abs=0.5)


def test_bias_wanders_slowly():
    quiet = GnssDegradation(noise_std_m=0.0, bias_std_m=8.0, bias_time_constant_s=20.0)
    error = PositionError(quiet, 7)
    first = error.step(0.033)
    second = error.step(0.033)
    assert math.dist(first, second) < 2.0


def test_reset_starts_again_from_zero_bias():
    quiet = GnssDegradation(noise_std_m=0.0, bias_std_m=8.0, bias_time_constant_s=20.0)
    error = PositionError(quiet, 7)
    for _ in range(1000):
        error.step(0.033)
    error.reset()
    assert math.hypot(*error.step(0.033)) < 2.0


def test_offset_position_moves_by_metres():
    lat, lon = 47.397971, 8.546164
    north, _ = offset_position(lat, lon, 111.0, 0.0)
    assert (north - lat) * 111_320.0 == pytest.approx(111.0, abs=0.5)
    _, east = offset_position(lat, lon, 0.0, 100.0)
    metres_per_deg = 111_320.0 * math.cos(math.radians(lat))
    assert (east - lon) * metres_per_deg == pytest.approx(100.0, abs=0.5)
