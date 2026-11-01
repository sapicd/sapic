# -*- coding: utf-8 -*-
USER = {
    "username": "alice",
    "password": "secret123",
    "email": "alice@example.com",
}


def register(client, **overrides):
    payload = dict(USER)
    payload.update(overrides)
    return client.post("/api/v1/auth/register", json=payload)


def login(client, username="alice", password="secret123"):
    response = client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]["csrf"]


def test_register_login_session_logout(client):
    response = register(client)
    assert response.status_code == 201
    body = response.get_json()
    assert body["data"]["user"]["username"] == "alice"
    assert "password_hash" not in body["data"]["user"]

    csrf = login(client)
    session = client.get("/api/v1/auth/session").get_json()["data"]
    assert session["authenticated"] is True
    assert session["user"]["username"] == "alice"

    response = client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 200
    assert client.get("/api/v1/auth/session").get_json()["data"]["authenticated"] is False


def test_duplicate_username(client):
    assert register(client).status_code == 201
    assert register(client, email="other@example.com").status_code == 409


def test_wrong_password(client):
    register(client)
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.get_json()["code"] == "UNAUTHORIZED"


def test_csrf_required_for_cookie_writes(client):
    register(client)
    login(client)
    response = client.post("/api/v1/auth/tokens", json={"name": "picgo"})
    assert response.status_code == 403
    assert response.get_json()["code"] == "FORBIDDEN"


def test_personal_access_token(app, client):
    register(client)
    csrf = login(client)
    response = client.post(
        "/api/v1/auth/tokens",
        json={"name": "picgo"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201
    token = response.get_json()["data"]["token"]
    assert token.startswith("sp_")

    other = app.test_client()
    session = other.get(
        "/api/v1/auth/session", headers={"Authorization": "Bearer %s" % token}
    ).get_json()["data"]
    assert session["authenticated"] is True
    assert session["user"]["username"] == "alice"


def test_password_reset_flow(client):
    register(client)
    response = client.post(
        "/api/v1/auth/password/forgot", json={"email": "alice@example.com"}
    )
    assert response.status_code == 202
    reset_token = response.get_json()["data"]["reset_token"]

    response = client.post(
        "/api/v1/auth/password/reset",
        json={"token": reset_token, "password": "newsecret123"},
    )
    assert response.status_code == 200

    login(client, password="newsecret123")


def test_password_change_revokes_other_sessions(app, client):
    register(client)
    first = app.test_client()
    first_csrf = login(first)

    second = app.test_client()
    second_csrf = login(second)

    response = second.put(
        "/api/v1/auth/password",
        json={"old_password": "secret123", "new_password": "newsecret123"},
        headers={"X-CSRF-Token": second_csrf},
    )
    assert response.status_code == 200

    assert first.get("/api/v1/auth/session").get_json()["data"]["authenticated"] is False
    assert second.get("/api/v1/auth/session").get_json()["data"]["authenticated"] is True


def test_update_profile(client):
    register(client)
    csrf = login(client)

    response = client.put(
        "/api/v1/auth/profile",
        json={"nickname": "爱丽丝", "email": "alice2@example.com", "avatar": "/a.png"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.get_json()
    user = response.get_json()["data"]["user"]
    assert user["nickname"] == "爱丽丝"
    assert user["email"] == "alice2@example.com"
    assert user["avatar"] == "/a.png"
    assert user["username"] == "alice"

    session = client.get("/api/v1/auth/session").get_json()["data"]
    assert session["user"]["nickname"] == "爱丽丝"


def test_update_profile_rejects_taken_email(client):
    register(client)
    client.post("/api/v1/auth/logout")
    register(client, username="bobby", email="bob@example.com")

    csrf = login(client, username="bobby")
    response = client.put(
        "/api/v1/auth/profile",
        json={"email": "alice@example.com"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 409
    assert response.get_json()["code"] == "CONFLICT"
