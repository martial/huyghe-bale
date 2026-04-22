"""Shape-test for /api/v1/health — the endpoint the launcher's error
dialog depends on and the frontend HealthBanner polls."""

import pytest

from app import create_app


@pytest.fixture
def client(tmp_path):
    # start_osc=False keeps the real UDP server out of unit tests.
    app = create_app(data_dir=str(tmp_path), start_osc=False)
    app.testing = True
    with app.test_client() as c:
        yield c


def test_health_payload_shape(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.get_json()

    # Every subsystem is reported, even when disabled.
    assert "osc_receiver" in body
    assert "bridge" in body
    assert "playback" in body
    assert "ok" in body
    assert "log_path" in body

    assert "running" in body["osc_receiver"]
    assert "port" in body["osc_receiver"]
    assert "error" in body["osc_receiver"]

    assert "running" in body["bridge"]
    assert "error" in body["bridge"]

    assert "thread_alive" in body["playback"]
    assert "last_error" in body["playback"]


def test_health_ok_true_when_no_errors(client):
    resp = client.get("/api/v1/health")
    body = resp.get_json()
    # Receiver didn't start (start_osc=False), but no error was recorded
    # either. Bridge is idle. Playback hasn't run. ok should be True.
    assert body["osc_receiver"]["error"] is None
    assert body["bridge"]["error"] is None
    assert body["playback"]["last_error"] is None
    assert body["ok"] is True
