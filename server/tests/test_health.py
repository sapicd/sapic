# -*- coding: utf-8 -*-

from sapic.version import __version__


def test_health_ok(client):
    response = client.get("/api/v2/health")
    assert response.status_code == 200

    body = response.get_json()
    assert body["code"] == "OK"
    assert body["data"]["database"] is True
    #: 探针之外还兼职报版本，排障时不用进后台看。
    assert body["data"]["version"] == __version__
    assert "redis" not in body["data"]
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
