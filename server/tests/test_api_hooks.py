# -*- coding: utf-8 -*-
"""Hook UI endpoints: catalogue, manifests, slots, actions and datasets."""

from sapic.models import User

USER = {
    "username": "alice",
    "password": "secret123",
    "email": "alice@example.com",
}


def signin(client, app=None, admin=False):
    client.post("/api/v1/auth/register", json=USER)
    response = client.post(
        "/api/v1/auth/login",
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
    assert client.get("/api/v1/hooks").status_code == 401


def test_catalogue_lists_installed_hooks(client):
    signin(client)

    body = client.get("/api/v1/hooks").get_json()
    items = {item["name"]: item for item in body["data"]["items"]}
    assert "up2local" in items
    assert items["up2local"]["catalog"] == "upload"
    #: Admin slots are hidden from ordinary users.
    assert all(not slot["name"].startswith("admin.") for slot in body["data"]["slots"])


def test_manifests_require_admin(app, client):
    signin(client)
    assert client.get("/api/v1/hooks/manifests").status_code == 403

    grant_admin(app)
    body = client.get("/api/v1/hooks/manifests").get_json()
    items = {item["name"]: item for item in body["data"]["items"]}
    local = items["up2local"]
    assert local["ui_version"] == 1
    assert local["config_schema"][0]["key"] == "root"
    assert [action["name"] for action in local["actions"]] == ["ping"]


def test_public_slot_is_anonymous(client):
    body = client.get("/api/v1/hooks/slots/login.after_form").get_json()
    assert body["data"]["blocks"] == []


def test_unknown_slot(client):
    assert client.get("/api/v1/hooks/slots/nope").status_code == 404


def test_admin_slot_is_denied_for_regular_users(client):
    signin(client)
    assert client.get("/api/v1/hooks/slots/admin.site_setting").status_code == 403


def test_admin_slot_renders_declarative_nodes(app, client):
    signin(client, app=app, admin=True)

    context = '{"backend": {"config": {"root": "/tmp"}, "in_use": true}}'
    body = client.get(
        "/api/v1/hooks/slots/admin.hook_setting",
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
    field = next(item for item in children if item["type"] == "input")
    assert field["default"] == "/tmp"


def test_invalid_context_is_rejected(app, client):
    signin(client, app=app, admin=True)
    response = client.get(
        "/api/v1/hooks/slots/admin.hook_setting",
        query_string={"context": "not-json"},
    )
    assert response.status_code == 400


def test_action_needs_a_csrf_token(app, client):
    signin(client, app=app, admin=True)
    response = client.post(
        "/api/v1/hooks/up2local/actions/ping", json={"values": {}}
    )
    assert response.status_code == 403


def test_action_reports_success(app, client, tmp_path):
    csrf = signin(client, app=app, admin=True)

    response = client.post(
        "/api/v1/hooks/up2local/actions/ping",
        json={"values": {"root": str(tmp_path)}},
        headers={"X-CSRF-Token": csrf},
    )
    data = response.get_json()["data"]
    assert data["code"] == 0
    assert data["toast"]["level"] == "success"


def test_action_business_failure_stays_in_the_body(app, client, tmp_path):
    csrf = signin(client, app=app, admin=True)

    response = client.post(
        "/api/v1/hooks/up2local/actions/ping",
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
        "/api/v1/hooks/up2local/actions/rm",
        "/api/v1/hooks/ghost/actions/ping",
    ):
        response = client.post(path, json={}, headers={"X-CSRF-Token": csrf})
        assert response.status_code == 404


def test_unknown_dataset_is_404(client):
    signin(client)
    response = client.get("/api/v1/hooks/up2local/data/missing")
    assert response.status_code == 404
