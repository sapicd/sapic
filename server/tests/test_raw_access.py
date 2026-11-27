# -*- coding: utf-8 -*-
"""``/raw`` access controls: link mode, rate limit, IP rules and the cache."""

import io

from sapic.libs.cache import RAW_KEY, Cache, get_cache
from sapic.libs.ratelimit import forget_rate_limit
from sapic.libs.settings import set_setting
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


def upload(client, csrf, name="raw.png"):
    response = client.post(
        "/api/v2/upload",
        data={"file": (io.BytesIO(b"raw-bytes"), name)},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]["image"]["sha"]


def set_site(app, **values):
    with app.app_context():
        for key, value in values.items():
            set_setting(key, value)


def test_link_mode_defaults_to_raw(app, client):
    """默认对外只给 /raw：公开图也不再暴露存储直链。"""
    csrf = register_and_login(client)
    upload(client, csrf)
    listing = client.get("/api/v2/images").get_json()["data"]["items"][0]
    assert listing["src"] == "http://localhost/raw/%s" % listing["sha"]


def test_empty_ip_list_disables_the_rule(app, client):
    csrf = register_and_login(client)
    sha = upload(client, csrf)
    set_site(app, raw_ip_mode="deny")

    #: 规则开着但列表为空：不能因此把全站图片锁死。
    assert client.get("/raw/%s" % sha).status_code == 200


def test_ip_deny_blocks_the_listed_network(app, client):
    csrf = register_and_login(client)
    sha = upload(client, csrf)
    assert client.get("/raw/%s" % sha).status_code == 200

    set_site(app, raw_ip_mode="deny", raw_ip_list="127.0.0.0/8")
    blocked = client.get("/raw/%s" % sha)
    assert blocked.status_code == 403
    #: 拒绝结果绝不能被缓存住。
    assert blocked.headers["Cache-Control"] == "no-store"


def test_ip_allow_list_must_cover_the_client(app, client):
    csrf = register_and_login(client)
    sha = upload(client, csrf)

    set_site(app, raw_ip_mode="allow", raw_ip_list="10.0.0.0/8")
    assert client.get("/raw/%s" % sha).status_code == 403

    set_site(app, raw_ip_mode="allow", raw_ip_list="127.0.0.1, 10.0.0.0/8")
    assert client.get("/raw/%s" % sha).status_code == 200


def test_ipv6_entries_do_not_match_ipv4_clients(app, client):
    csrf = register_and_login(client)
    sha = upload(client, csrf)

    set_site(app, raw_ip_mode="allow", raw_ip_list="::1/128")
    #: 测试客户端是 IPv4；v6 规则不该误伤 v4 请求（版本不同 = 不在列表内）。
    assert client.get("/raw/%s" % sha).status_code == 403


def test_raw_rate_limit_is_separate_from_the_api_budget(app, client):
    csrf = register_and_login(client)
    sha = upload(client, csrf)
    set_site(app, raw_rate_limit=2)
    with app.app_context():
        forget_rate_limit(reset=True)

    assert client.get("/raw/%s" % sha).status_code == 200
    assert client.get("/raw/%s" % sha).status_code == 200

    blocked = client.get("/raw/%s" % sha)
    assert blocked.status_code == 429
    assert 1 <= int(blocked.headers["Retry-After"]) <= 61

    #: 图片预算用尽不影响 API，反之亦然。
    assert client.get("/api/v2/site").status_code == 200


def test_zero_disables_the_raw_limit(app, client):
    csrf = register_and_login(client)
    sha = upload(client, csrf)
    set_site(app, raw_rate_limit=0)
    with app.app_context():
        forget_rate_limit(reset=True)

    for _ in range(5):
        assert client.get("/raw/%s" % sha).status_code == 200


def test_resolved_target_is_cached_and_invalidated_on_delete(app, client):
    csrf = register_and_login(client)
    sha = upload(client, csrf)
    assert client.get("/raw/%s" % sha).status_code == 200

    with app.app_context():
        assert get_cache().get(RAW_KEY % (sha, 0))

    removed = client.delete(
        "/api/v2/images/%s" % sha, headers={"X-CSRF-Token": csrf}
    )
    assert removed.status_code == 200, removed.get_json()

    with app.app_context():
        assert get_cache().get(RAW_KEY % (sha, 0)) is None


def test_memory_cache_honours_ttl_and_prefix(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("sapic.libs.cache.monotonic", lambda: now[0])
    cache = Cache()
    assert cache.backend == "memory"

    cache.set("sapic:raw:a:0", "a", 10)
    cache.set("sapic:raw:b:0", "b", 10)
    assert cache.get("sapic:raw:a:0") == "a"

    now[0] += 11
    assert cache.get("sapic:raw:a:0") is None

    cache.set("sapic:raw:a:0", "a", 10)
    cache.clear_prefix("sapic:raw:")
    assert cache.get("sapic:raw:a:0") is None


def test_redis_backend_is_used_when_reachable(monkeypatch):
    """配置了地址就走 Redis；这里用假客户端验证调用的是哪套接口。"""

    class FakeRedis:
        def __init__(self):
            self.store = {}

        def ping(self):
            return True

        def get(self, key):
            return self.store.get(key)

        def set(self, key, value, ex=None):
            self.store[key] = value

        def delete(self, *keys):
            for key in keys:
                self.store.pop(key, None)

        def scan_iter(self, match=None, count=None):
            prefix = (match or "").rstrip("*")
            return [key for key in list(self.store) if key.startswith(prefix)]

    monkeypatch.setattr(
        "sapic.libs.cache.redis.Redis.from_url",
        lambda *args, **kwargs: FakeRedis(),
    )
    cache = Cache("redis://cache:6379/0")
    assert cache.backend == "redis"

    cache.set("sapic:raw:a:0", "a", 30)
    assert cache.get("sapic:raw:a:0") == "a"
    cache.clear_prefix("sapic:raw:")
    assert cache.get("sapic:raw:a:0") is None


def test_raw_settings_are_validated_and_normalised(app, client):
    csrf = register_and_login(client)
    promote_admin(app)
    headers = {"X-CSRF-Token": csrf}

    for payload in (
        {"link_mode": "weird"},
        {"raw_ip_mode": "maybe"},
        {"raw_ip_list": "not-an-ip"},
        {"raw_rate_limit": -1},
        {"raw_rate_limit": 60001},
    ):
        response = client.put("/api/v2/settings", json=payload, headers=headers)
        assert response.status_code == 400, payload
        assert response.get_json()["code"] == "PARAM_ERROR"

    response = client.put(
        "/api/v2/settings",
        json={
            "link_mode": "direct",
            "raw_ip_mode": "deny",
            "raw_ip_list": "10.0.0.0/8, 192.168.1.10",
            "raw_rate_limit": 300,
            "hotlink_allow_empty": False,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.get_json()
    items = response.get_json()["data"]["items"]
    assert items["link_mode"] == "direct"
    assert items["raw_ip_mode"] == "deny"
    #: 单个地址按 /32 归一，重复项去重。
    assert items["raw_ip_list"] == "10.0.0.0/8,192.168.1.10/32"
    assert items["raw_rate_limit"] == 300
    assert items["hotlink_allow_empty"] is False
