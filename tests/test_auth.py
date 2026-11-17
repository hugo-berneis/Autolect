"""Auth: password login -> cookie protects HTTP + WebSocket; login rate limit."""
from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect


def _reset_rate_limit():
    from app import auth

    auth._failures.clear()


def test_requires_auth(rawclient):
    _reset_rate_limit()
    assert rawclient.get("/api/lectures").status_code == 401


def test_login_wrong_then_right(rawclient):
    _reset_rate_limit()
    assert rawclient.post("/api/login", json={"password": "nope"}).status_code == 401
    assert rawclient.get("/api/lectures").status_code == 401

    assert rawclient.post("/api/login", json={"password": "secret"}).status_code == 200
    assert rawclient.get("/api/lectures").status_code == 200  # cookie now set
    assert rawclient.get("/api/me").json()["user"] == "default"

    rawclient.post("/api/logout")
    assert rawclient.get("/api/lectures").status_code == 401


def test_login_rate_limited(rawclient):
    _reset_rate_limit()
    for _ in range(5):  # default limit is 5 failures/min
        assert rawclient.post("/api/login", json={"password": "x"}).status_code == 401
    assert rawclient.post("/api/login", json={"password": "x"}).status_code == 429
    # even the correct password is blocked while rate-limited
    assert rawclient.post("/api/login", json={"password": "secret"}).status_code == 429


def test_websocket_requires_auth(rawclient):
    _reset_rate_limit()
    with pytest.raises(WebSocketDisconnect):
        with rawclient.websocket_connect("/ws/record") as ws:
            ws.send_json({"type": "start", "title": "x"})
            ws.receive_json()

    rawclient.post("/api/login", json={"password": "secret"})
    with rawclient.websocket_connect("/ws/record") as ws:
        ws.send_json({"type": "start", "title": "Authed"})
        assert ws.receive_json()["type"] == "ready"
        ws.send_json({"type": "stop"})
        # drain to stopped
        for _ in range(50):
            if ws.receive_json()["type"] == "stopped":
                break
