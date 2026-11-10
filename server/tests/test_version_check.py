# -*- coding: utf-8 -*-
"""Update check: version comparison and the admin console endpoint."""

import pytest

from sapic.libs import release
from sapic.models import User
from sapic.utils.common import is_newer_version

USER = {
    "username": "carol",
    "password": "secret123",
    "email": "carol@example.com",
}


@pytest.fixture(autouse=True)
def _clear_release_cache():
    release.clear_cache()
    yield
    release.clear_cache()


@pytest.mark.parametrize(
    ("latest", "current"),
    [
        ("2.1.0", "2.0.0"),
        ("v2.1.0", "2.0.0"),
        ("2.0.1", "2.0.0"),
        ("2.1", "2.0.9"),
        ("2.0.0", "2.0.0.dev0"),
        ("2.0.0", "2.0.0-rc1"),
    ],
)
def test_newer_releases(latest, current):
    assert is_newer_version(latest, current)


@pytest.mark.parametrize(
    ("latest", "current"),
    [
        ("2.0.0", "2.0.0"),
        ("v2.0.0", "2.0"),
        ("2.0.0-rc1", "2.0.0"),
        ("1.9.9", "2.0.0"),
        ("", "2.0.0"),
        ("latest", "2.0.0"),
    ],
)
def test_not_newer(latest, current):
    assert not is_newer_version(latest, current)


def signin_admin(client, app):
    client.post("/api/v2/auth/register", json=USER)
    response = client.post(
        "/api/v2/auth/login",
        json={"username": USER["username"], "password": USER["password"]},
    )
    assert response.status_code == 200, response.get_json()
    with app.app_context():
        User.update(is_admin=True).where(User.username == USER["username"]).execute()


def test_version_endpoint_requires_admin(client, app):
    client.post("/api/v2/auth/register", json=USER)
    client.post(
        "/api/v2/auth/login",
        json={"username": USER["username"], "password": USER["password"]},
    )
    assert client.get("/api/v2/settings/version").status_code == 403


def test_version_endpoint_reports_update(app, client, monkeypatch):
    signin_admin(client, app)
    calls = []

    def fake_fetch(url):
        calls.append(url)
        return {
            "tag_name": "v2.1.0",
            "published_at": "2026-01-02T03:04:05Z",
            "html_url": "https://example.com/release",
        }

    monkeypatch.setattr(release, "_fetch", fake_fetch)

    body = client.get("/api/v2/settings/version").get_json()
    data = body["data"]
    assert data["current"] == release.__version__
    assert data["latest"] == "v2.1.0"
    assert data["has_update"] is True
    assert data["released_at"] > 0
    assert data["url"] == "https://example.com/release"
    assert data["cached"] is False

    #: 24 小时缓存：第二次不再请求远端。
    again = client.get("/api/v2/settings/version").get_json()["data"]
    assert again["cached"] is True
    assert len(calls) == 1

    #: ?refresh=1 强制重新拉取。
    client.get("/api/v2/settings/version?refresh=1")
    assert len(calls) == 2


def test_version_endpoint_degrades_when_fetch_fails(app, client, monkeypatch):
    signin_admin(client, app)

    def boom(url):
        raise OSError("network down")

    monkeypatch.setattr(release, "_fetch", boom)
    data = client.get("/api/v2/settings/version").get_json()["data"]
    assert data["has_update"] is False
    assert data["latest"] == ""
    assert data["error"]


def test_version_check_can_be_disabled(app, client, monkeypatch):
    signin_admin(client, app)
    monkeypatch.setitem(app.config, "UPDATE_CHECK_URL", "")

    def boom(url):  # pragma: no cover - must not be called
        raise AssertionError("fetch should not run when disabled")

    monkeypatch.setattr(release, "_fetch", boom)
    data = client.get("/api/v2/settings/version").get_json()["data"]
    assert data["enabled"] is False
    assert data["has_update"] is False
