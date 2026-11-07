# -*- coding: utf-8 -*-
import io

import pytest

from sapic.basis.errors import ApiError
from sapic.utils.common import host_allowed, parse_allow_hosts, validate_allow_hosts

USER = {"username": "alice", "password": "secret123", "email": "alice@example.com"}
FOREIGN = {"Referer": "https://evil.example/post"}


def register(client):
    client.post("/api/v2/auth/register", json=USER)
    response = client.post(
        "/api/v2/auth/login",
        json={"username": USER["username"], "password": USER["password"]},
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]["csrf"]


def upload(client, csrf, name="hotlink.png"):
    response = client.post(
        "/api/v2/uploads",
        data={"file": (io.BytesIO(b"hotlink-bytes"), name)},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]["image"]["sha"]


def set_prefs(client, csrf, **prefs):
    response = client.put(
        "/api/v2/auth/settings", json=prefs, headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]["settings"]


def test_allow_list_is_normalised():
    assert (
        validate_allow_hosts(" Blog.Example.COM:8080, *.Foo.org,,")
        == "blog.example.com,*.foo.org"
    )
    #: 贴一整个 URL 也认，取它的 host。
    assert validate_allow_hosts("https://img.example.com/a.png") == "img.example.com"
    assert validate_allow_hosts("  ") == ""


def test_unusable_host_is_rejected():
    with pytest.raises(ApiError):
        validate_allow_hosts("bad host!")


def test_wildcard_matches_subdomains_only():
    patterns = parse_allow_hosts("img.example.com,*.example.org")
    assert host_allowed("IMG.example.com", patterns)
    assert host_allowed("a.b.example.org", patterns)
    #: 通配不覆盖 apex，也不能用 query 伪造成白名单域名。
    assert not host_allowed("example.org", patterns)
    assert not host_allowed("evil.example/?u=img.example.com", patterns)


def test_hotlink_is_off_until_the_owner_asks(client):
    csrf = register(client)
    sha = upload(client, csrf)

    assert client.get("/raw/%s" % sha, headers=FOREIGN).status_code == 200

    set_prefs(client, csrf, hotlink_enabled=True)

    blocked = client.get("/raw/%s" % sha, headers=FOREIGN)
    assert blocked.status_code == 403
    #: /raw 平时给一年 immutable，拒绝结果绝不能跟着被缓存。
    assert blocked.headers["Cache-Control"] == "no-store"

    passed = client.get("/raw/%s" % sha, headers={"Referer": "http://localhost/x"})
    assert passed.status_code == 200
    #: 判定依赖 Referer，共享缓存必须按它分区。
    assert "private" in passed.headers["Cache-Control"]
    assert "Referer" in passed.headers.get("Vary", "")


def test_empty_referer_can_be_rejected(client):
    csrf = register(client)
    sha = upload(client, csrf)
    set_prefs(client, csrf, hotlink_enabled=True)

    #: 默认放行空来源：直开图片、聊天工具预览都不带 Referer。
    assert client.get("/raw/%s" % sha).status_code == 200

    set_prefs(client, csrf, hotlink_allow_empty=False)
    assert client.get("/raw/%s" % sha).status_code == 403


def test_allow_list_lets_the_owners_sites_through(client):
    csrf = register(client)
    sha = upload(client, csrf)
    set_prefs(
        client,
        csrf,
        hotlink_enabled=True,
        hotlink_allow_hosts="blog.example.com,*.example.org",
    )

    url = "/raw/%s" % sha
    assert client.get(url, headers={"Referer": "https://blog.example.com/p/1"}).status_code == 200
    assert client.get(url, headers={"Referer": "https://a.example.org/"}).status_code == 200
    assert client.get(url, headers={"Referer": "https://example.org/"}).status_code == 403
    assert client.get(url, headers={"Referer": "https://evil.example/"}).status_code == 403


def test_private_images_are_not_affected(app, client):
    csrf = register(client)
    sha = upload(client, csrf)
    response = client.patch(
        "/api/v2/images/%s" % sha,
        json={"visibility": "private"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.get_json()
    set_prefs(client, csrf, hotlink_enabled=True, hotlink_allow_empty=False)

    #: 私有图靠 can_view 而不是防盗链，带会话照常可读。
    assert client.get("/raw/%s" % sha, headers=FOREIGN).status_code == 200
    #: 匿名访问仍然被鉴权挡住。
    anonymous = app.test_client()
    assert anonymous.get("/raw/%s" % sha).status_code == 403


def test_settings_normalise_and_reject_hosts(client):
    csrf = register(client)
    settings = set_prefs(
        client, csrf, hotlink_allow_hosts=" Blog.Example.com:443 ,*.foo.org "
    )
    assert settings["hotlink_allow_hosts"] == "blog.example.com,*.foo.org"

    bad = client.put(
        "/api/v2/auth/settings",
        json={"hotlink_allow_hosts": "http://#"},
        headers={"X-CSRF-Token": csrf},
    )
    assert bad.status_code == 400
