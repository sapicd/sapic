# -*- coding: utf-8 -*-


def test_health_ok(client):
    response = client.get("/api/v2/health")
    assert response.status_code == 200

    body = response.get_json()
    assert body["code"] == "OK"
    assert body["data"]["database"] is True
    # Redis is optional and not configured in tests.
    assert body["data"]["redis"] is None
    assert response.headers.get("X-Request-Id")


def test_root_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.get_json()["data"]["service"] == "sapic"


def test_unknown_route_returns_json(client):
    response = client.get("/api/v2/not-exists")
    assert response.status_code == 404
    body = response.get_json()
    assert body["code"] == "NOT_FOUND"
    assert body["request_id"]
