"""Playback threads must not die silently — a crash in the loop body
used to kill the daemon thread while `self.playing` stayed True,
so the UI reported a show that wasn't actually running.

Each _run_* method wraps its body in try/except that records
`self._last_error` and flips `self.playing = False` in a finally.
"""

import time
from unittest.mock import patch

import pytest

from engine.playback import PlaybackEngine


@pytest.fixture
def engine():
    e = PlaybackEngine(tick_rate=60)
    yield e
    e.stop()


def _wait_stopped(engine, timeout=1.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not engine.playing:
            return True
        time.sleep(0.01)
    return False


def test_timeline_crash_surfaces_last_error(engine):
    """If evaluate_lane blows up mid-playback, the thread exits cleanly,
    playing flips to False, and last_error is populated."""
    timeline = {
        "id": "tl_boom",
        "duration": 10.0,
        "lanes": {
            "a": {"points": [{"time": 0, "value": 0.0}]},
            "b": {"points": [{"time": 0, "value": 0.0}]},
        },
    }

    with patch("engine.playback.evaluate_lane", side_effect=RuntimeError("boom")):
        engine.start_timeline(timeline, devices=[])
        assert _wait_stopped(engine)

    assert engine.playing is False
    assert engine.last_error is not None
    assert "boom" in engine.last_error
    status = engine.status()
    assert status["playing"] is False
    assert status["last_error"] == engine.last_error


def test_last_error_cleared_on_next_run(engine):
    """After a crash, starting a new run clears the stale error."""
    timeline = {
        "id": "tl_boom",
        "duration": 10.0,
        "lanes": {"a": {"points": []}, "b": {"points": []}},
    }
    with patch("engine.playback.evaluate_lane", side_effect=RuntimeError("boom")):
        engine.start_timeline(timeline, devices=[])
        assert _wait_stopped(engine)
    assert engine.last_error is not None

    # New run clears the error synchronously, before the thread even spawns.
    engine.start_timeline(timeline, devices=[])
    assert engine.last_error is None


def test_thread_alive_property(engine):
    timeline = {
        "id": "tl_idle",
        "duration": 10.0,
        "lanes": {"a": {"points": []}, "b": {"points": []}},
    }
    assert engine.thread_alive is False
    engine.start_timeline(timeline, devices=[])
    assert engine.thread_alive is True
    engine.stop()
    assert engine.thread_alive is False
