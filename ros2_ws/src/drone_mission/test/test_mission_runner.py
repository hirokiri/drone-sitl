"""Unit tests for the mission runner's setpoint helper."""

import pytest
from drone_mission.mission_runner import advance_setpoint


def test_advance_setpoint_moves_by_the_step():
    assert advance_setpoint((0.0, 0.0, 0.0), (10.0, 0.0, 0.0), 2.5) == (2.5, 0.0, 0.0)


def test_advance_setpoint_keeps_direction():
    assert advance_setpoint((0.0, 0.0, 0.0), (3.0, 4.0, 0.0), 1.0) == pytest.approx(
        (0.6, 0.8, 0.0)
    )


def test_advance_setpoint_does_not_overshoot():
    target = (1.0, 1.0, -1.0)
    assert advance_setpoint((0.9, 1.0, -1.0), target, 0.5) == target
    assert advance_setpoint(target, target, 0.5) == target
