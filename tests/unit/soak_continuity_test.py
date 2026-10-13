"""Suspend and clock correction must never become observation evidence."""

import pytest

from scripts import soak_acceptance as soak


@pytest.mark.parametrize(
    "mono,wall,reason",
    [
        (86401, 86401, "OBSERVATION_GAP"),
        (30, 3630, "CLOCK_DISCONTINUITY"),  # monotonic excludes suspension
        (30, 29.4, "CLOCK_DISCONTINUITY"),  # backward wall adjustment
        (30, 30.6, "CLOCK_DISCONTINUITY"),
        (-1, 1, "CLOCK_DISCONTINUITY"),
    ],
)
def test_unobserved_or_discontinuous_time_is_rejected(monkeypatch, mono, wall, reason):
    monkeypatch.setattr(soak.time, "monotonic", lambda: 1000 + mono)
    monkeypatch.setattr(soak.time, "time", lambda: 10000 + wall)
    with pytest.raises(RuntimeError, match=reason):
        soak.observe_continuity((1000, 10000), 30)


def test_normal_cadence_and_bounded_restart_work_remain_valid(monkeypatch):
    monkeypatch.setattr(soak.time, "monotonic", lambda: 1045)
    monkeypatch.setattr(soak.time, "time", lambda: 10045.02)
    assert soak.observe_continuity((1000, 10000), 30) == (1045, 10045.02)
