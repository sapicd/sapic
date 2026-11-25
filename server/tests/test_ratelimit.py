# -*- coding: utf-8 -*-
"""API rate limiting: fixed windows, the 429 envelope and the settings bound."""

import pytest
from flask import g

from sapic.libs import ratelimit
from sapic.models import User


def register_and_login(client, username="alice"):
    client.post(
        "/api/v2/auth/register",
        json={
            "username": username,
            "password": "secret123",
            "email": "%s@example.com" % username,
        },
    )
    response = client.post(
        "/api/v2/auth/login",
        json={"username": username, "password": "secret123"},
    )
    return response.get_json()["data"]["csrf"]


def promote_admin(app, username="alice"):
    with app.app_context():
        user = User.get(User.username == username)
        user.is_admin = True
        user.save(only=[User.is_admin])


@pytest.fixture()
def admin(app, client):
    csrf = register_and_login(client)
    promote_admin(app)
    return csrf


def set_limit(client, csrf, value):
    response = client.put(
        "/api/v2/settings",
        json={"api_rate_limit": value},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.get_json()
    return response


def test_limiter_counts_within_the_window():
    limiter = ratelimit.RateLimiter()
    assert limiter.check("ip:a", 2, now=0) == (True, 0)
    assert limiter.check("ip:a", 2, now=59) == (True, 0)

    allowed, retry_after = limiter.check("ip:a", 2, now=59)
    assert allowed is False
    assert retry_after == 2

    #: 其它客户端不受影响，下一分钟自动重置。
    assert limiter.check("ip:b", 2, now=59) == (True, 0)
    assert limiter.check("ip:a", 2, now=60) == (True, 0)


def test_limiter_evicts_the_oldest_key_when_full():
    limiter = ratelimit.RateLimiter(max_keys=2)
    limiter.check("a", 10, now=0)
    limiter.check("b", 10, now=0)
    limiter.check("c", 10, now=0)

    assert set(limiter._buckets) == {"b", "c"}


def test_limiter_caches_the_setting_until_forgotten(monkeypatch):
    calls = []

    def fake_setting(key):
        calls.append(key)
        return 7

    monkeypatch.setattr(ratelimit, "get_setting", fake_setting)
    limiter = ratelimit.RateLimiter(config_ttl=60)

    assert limiter.limit() == 7
    assert limiter.limit() == 7
    assert calls == ["api_rate_limit"]

    limiter.forget()
    assert limiter.limit() == 7
    assert len(calls) == 2


def test_invalid_setting_disables_limiting(monkeypatch):
    monkeypatch.setattr(ratelimit, "get_setting", lambda key: "oops")
    limiter = ratelimit.RateLimiter(config_ttl=60)
    assert limiter.limit() == 0


def test_client_key_prefers_the_signed_in_user(app):
    class Someone:
        id = 42

    with app.test_request_context(
        "/api/v2/site", environ_base={"REMOTE_ADDR": "203.0.113.9"}
    ):
        g.user = None
        assert ratelimit.client_key() == "ip:203.0.113.9"
        g.user = Someone()
        assert ratelimit.client_key() == "u:42"


def test_default_limit_is_120_per_minute(app, client, admin):
    items = client.get("/api/v2/settings").get_json()["data"]["items"]
    assert items["api_rate_limit"] == 120


def test_api_requests_return_429_with_retry_after(app, client, admin):
    set_limit(client, admin, 2)

    assert client.get("/api/v2/site").status_code == 200
    assert client.get("/api/v2/site").status_code == 200

    blocked = client.get("/api/v2/site")
    assert blocked.status_code == 429
    assert blocked.get_json()["code"] == "RATE_LIMITED"
    assert 1 <= int(blocked.headers["Retry-After"]) <= 61

    #: 健康检查不计数也不被拦，负载均衡的探针不会因为限速掉线。
    assert client.get("/api/v2/health").status_code == 200
    assert client.get("/api/v2/site").status_code == 429


def test_zero_disables_the_limit(app, client, admin):
    set_limit(client, admin, 0)
    for _ in range(5):
        assert client.get("/api/v2/site").status_code == 200


@pytest.mark.parametrize("value", (-1, 6001))
def test_limit_setting_is_bounded(app, client, admin, value):
    response = client.put(
        "/api/v2/settings",
        json={"api_rate_limit": value},
        headers={"X-CSRF-Token": admin},
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "PARAM_ERROR"
