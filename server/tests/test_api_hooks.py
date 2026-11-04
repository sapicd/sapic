# -*- coding: utf-8 -*-
"""Hook UI endpoints: catalogue, manifests, slots, actions and datasets."""

from sapic.models import User

USER = {
    "username": "alice",
    "password": "secret123",
    "email": "alice@example.com",
}


def signin(client, app=None, admin=False):
    client.post("/api/v2/auth/register", json=USER)
    response = client.post(
        "/api/v2/auth/login",
        json={"username": USER["username"], "password": USER["password"]},
    )
    assert response.status_code == 200, response.get_json()
    if admin and app is not None:
        with app.app_context():
            User.update(is_admin=True).where(
                User.username == USER["username"]
            ).execute()
    return response.get_json()["data"]["csrf"]


def grant_admin(app):
    """Promote the current session user without logging in again."""
    with app.app_context():
        User.update(is_admin=True).where(
            User.username == USER["username"]
        ).execute()


def test_catalogue_requires_login(client):
    assert client.get("/api/v2/hooks").status_code == 401


def test_catalogue_lists_installed_hooks(client):
    signin(client)

    body = client.get("/api/v2/hooks").get_json()
    items = {item["name"]: item for item in body["data"]["items"]}
    assert "up2local" in items
    assert items["up2local"]["catalog"] == "upload"
    assert items["up2local"]["author"] == "staugur"
    #: Admin slots are hidden from ordinary users; ``slots`` is a name list.
    assert body["data"]["slots"] == ["login.after_form"]


def test_manifests_require_admin(app, client):
    signin(client)
    assert client.get("/api/v2/hooks/manifests").status_code == 403

    grant_admin(app)
    body = client.get("/api/v2/hooks/manifests").get_json()
    items = {item["name"]: item for item in body["data"]["items"]}
    local = items["up2local"]
    assert local["ui_version"] == 1
    assert local["config_schema"][0]["key"] == "domain"
    assert [action["name"] for action in local["actions"]] == ["ping"]


def test_public_slot_is_anonymous(client):
    body = client.get("/api/v2/hooks/slots/login.after_form").get_json()
    assert body["data"]["blocks"] == []


def test_unknown_slot(client):
    assert client.get("/api/v2/hooks/slots/nope").status_code == 404


def test_admin_slot_is_denied_for_regular_users(client):
    signin(client)
    assert client.get("/api/v2/hooks/slots/admin.site_setting").status_code == 403


def test_admin_slot_renders_declarative_nodes(app, client):
    signin(client, app=app, admin=True)

    context = '{"backend": {"config": {"root": "/tmp"}, "in_use": true}}'
    body = client.get(
        "/api/v2/hooks/slots/admin.hook_setting",
        query_string={"context": context},
    ).get_json()

    blocks = body["data"]["blocks"]
    assert [block["hook"] for block in blocks] == ["up2local"]
    nodes = blocks[0]["nodes"]
    assert nodes[0]["type"] == "fieldset"
    children = nodes[0]["children"]
    assert children[0]["type"] == "alert"
    button = next(item for item in children if item["type"] == "button")
    assert button["action"] == "ping"
    field = next(
        item
        for item in children
        if item["type"] == "input" and item["key"] == "root"
    )
    assert field["default"] == "/tmp"



def test_invalid_context_is_rejected(app, client):
    signin(client, app=app, admin=True)
    response = client.get(
        "/api/v2/hooks/slots/admin.hook_setting",
        query_string={"context": "not-json"},
    )
    assert response.status_code == 400


def test_action_needs_a_csrf_token(app, client):
    signin(client, app=app, admin=True)
    response = client.post(
        "/api/v2/hooks/up2local/actions/ping", json={"values": {}}
    )
    assert response.status_code == 403


def test_action_reports_success(app, client, tmp_path):
    csrf = signin(client, app=app, admin=True)

    response = client.post(
        "/api/v2/hooks/up2local/actions/ping",
        json={"values": {"root": str(tmp_path)}},
        headers={"X-CSRF-Token": csrf},
    )
    data = response.get_json()["data"]
    assert data["code"] == 0
    assert data["toast"]["level"] == "success"


def test_action_business_failure_stays_in_the_body(app, client, tmp_path):
    csrf = signin(client, app=app, admin=True)

    response = client.post(
        "/api/v2/hooks/up2local/actions/ping",
        json={"values": {"root": str(tmp_path / "missing")}},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["code"] == 1
    assert "does not exist" in data["message"]


def test_undeclared_action_or_hook_is_404(app, client):
    csrf = signin(client, app=app, admin=True)

    for path in (
        "/api/v2/hooks/up2local/actions/rm",
        "/api/v2/hooks/ghost/actions/ping",
    ):
        response = client.post(path, json={}, headers={"X-CSRF-Token": csrf})
        assert response.status_code == 404


def test_unknown_dataset_is_404_for_admins(app, client):
    signin(client, app=app, admin=True)
    response = client.get("/api/v2/hooks/up2local/data/missing")
    assert response.status_code == 404


def test_admin_scoped_endpoints_reject_normal_users(client):
    csrf = signin(client)
    #: 数据集是后台表格用途，普通用户一律 403，连数据源是否存在都不透露。
    assert client.get("/api/v2/hooks/up2local/data/missing").status_code == 403
    #: up2local 的 ping 声明了 scope=admin，普通用户不能借它探测服务器目录。
    response = client.post(
        "/api/v2/hooks/up2local/actions/ping",
        json={"values": {"root": "/tmp"}},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 403


def test_state_is_persisted_and_overrides_the_file_default(app, client):
    csrf = signin(client, app=app, admin=True)

    items = {
        item["name"]: item
        for item in client.get("/api/v2/hooks").get_json()["data"]["items"]
    }
    assert items["up2github"]["enabled"] is False

    response = client.patch(
        "/api/v2/hooks/up2github",
        json={"enabled": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["enabled"] is True

    items = {
        item["name"]: item
        for item in client.get("/api/v2/hooks").get_json()["data"]["items"]
    }
    assert items["up2github"]["enabled"] is True

    with app.app_context():
        manager = app.extensions["hooks"]
        assert manager.get("up2github").enabled is True
        senders = {
            result.get("sender")
            for result in manager.call("upimg_save", filename="", stream=b"")
        }
        assert "up2github" in senders


def test_state_needs_admin_and_a_boolean(app, client):
    csrf = signin(client)
    response = client.patch(
        "/api/v2/hooks/up2github",
        json={"enabled": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 403

    grant_admin(app)
    response = client.patch(
        "/api/v2/hooks/up2github",
        json={"enabled": "yes"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "PARAM_ERROR"

    response = client.patch(
        "/api/v2/hooks/ghost",
        json={"enabled": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 404


def test_reload_returns_the_catalogue(app, client):
    csrf = signin(client, app=app, admin=True)

    response = client.post("/api/v2/hooks/reload", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    names = {item["name"] for item in response.get_json()["data"]["items"]}
    assert {"up2local", "up2github", "pic2webp"} <= names


def test_config_roundtrip(app, client):
    csrf = signin(client, app=app, admin=True)

    items = {
        item["name"]: item
        for item in client.get("/api/v2/hooks/config").get_json()["data"]["items"]
    }
    assert set(items["up2local"]["values"]) == {"root", "domain"}
    #: 没有 config_schema 的钩子不进入配置页。
    assert "pic2webp" not in items

    response = client.put(
        "/api/v2/hooks/config/up2local",
        json={"root": "/srv/images"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["values"] == {"root": "/srv/images"}

    items = {
        item["name"]: item
        for item in client.get("/api/v2/hooks/config").get_json()["data"]["items"]
    }
    assert items["up2local"]["values"]["root"] == "/srv/images"


def test_config_rejects_unknown_keys(app, client):
    csrf = signin(client, app=app, admin=True)

    response = client.put(
        "/api/v2/hooks/config/up2local",
        json={"nope": "x"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 400
    assert "unknown config key" in response.get_json()["message"]


def test_config_requires_admin(client):
    signin(client)
    assert client.get("/api/v2/hooks/config").status_code == 403


def test_import_and_remove_a_third_party_hook(app, client, tmp_path, monkeypatch):
    from uuid import uuid4

    name = "demo_hook_%s" % uuid4().hex[:8]
    (tmp_path / ("%s.py" % name)).write_text(
        '__version__ = "1.0.0"\n__author__ = "tester"\n\n'
        'def hook_manifest():\n    return {"title": "Demo", "catalog": "auth"}\n',
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    csrf = signin(client, app=app, admin=True)

    response = client.post(
        "/api/v2/hooks/import",
        json={"module": name},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.get_json()
    item = response.get_json()["data"]["item"]
    assert item["name"] == name
    assert item["family"] == "third"

    names = {
        entry["name"]
        for entry in client.get("/api/v2/hooks").get_json()["data"]["items"]
    }
    assert name in names

    response = client.delete(
        "/api/v2/hooks/import/%s" % name, headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 200

    names = {
        entry["name"]
        for entry in client.get("/api/v2/hooks").get_json()["data"]["items"]
    }
    assert name not in names


def test_import_rejects_invalid_and_non_hook_modules(app, client):
    csrf = signin(client, app=app, admin=True)

    #: ``../etc/passwd`` is not a module name; ``os`` has no
    #: ``__version__``/``__author__``, so it cannot be a hook.
    for module in ("../etc/passwd", "os"):
        response = client.post(
            "/api/v2/hooks/import",
            json={"module": module},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 400, module

    names = {
        entry["name"]
        for entry in client.get("/api/v2/hooks").get_json()["data"]["items"]
    }
    assert "os" not in names


def test_local_hooks_are_marked_as_local(app, client):
    signin(client, app=app, admin=True)

    items = {
        entry["name"]: entry
        for entry in client.get("/api/v2/hooks").get_json()["data"]["items"]
    }
    assert items["up2local"]["family"] == "local"
