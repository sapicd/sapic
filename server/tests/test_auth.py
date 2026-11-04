# -*- coding: utf-8 -*-
import io

from sapic.libs.albums import default_album
from sapic.models import Image, User
from sapic.views.auth import _safe_next

USER = {
    "username": "alice",
    "password": "secret123",
    "email": "alice@example.com",
}


def register(client, **overrides):
    payload = dict(USER)
    payload.update(overrides)
    return client.post("/api/v2/auth/register", json=payload)


def login(client, username="alice", password="secret123"):
    response = client.post(
        "/api/v2/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]["csrf"]


def test_post_login_redirect_stays_on_site():
    """`\\` 会被浏览器归一成 `/`，`/\\evil.com` 等同站外跳转。"""
    assert _safe_next("/albums") == "/albums"
    assert _safe_next("//evil.com") == "/"
    assert _safe_next("/\\evil.com") == "/"
    assert _safe_next("https://evil.com") == "/"


def test_register_login_session_logout(client):
    response = register(client)
    assert response.status_code == 201
    body = response.get_json()
    assert body["data"]["user"]["username"] == "alice"
    assert "password_hash" not in body["data"]["user"]

    csrf = login(client)
    session = client.get("/api/v2/auth/session").get_json()["data"]
    assert session["authenticated"] is True
    assert session["user"]["username"] == "alice"

    response = client.post(
        "/api/v2/auth/logout", headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 200
    assert client.get("/api/v2/auth/session").get_json()["data"]["authenticated"] is False


def test_duplicate_username(client):
    assert register(client).status_code == 201
    assert register(client, email="other@example.com").status_code == 409


def test_wrong_password(client):
    register(client)
    response = client.post(
        "/api/v2/auth/login",
        json={"username": "alice", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.get_json()["code"] == "UNAUTHORIZED"


def test_csrf_required_for_cookie_writes(client):
    register(client)
    login(client)
    response = client.post("/api/v2/auth/tokens", json={"name": "picgo"})
    assert response.status_code == 403
    assert response.get_json()["code"] == "FORBIDDEN"


def test_personal_access_token(app, client):
    register(client)
    csrf = login(client)
    response = client.post(
        "/api/v2/auth/tokens",
        json={"name": "picgo"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201
    token = response.get_json()["data"]["token"]
    assert token.startswith("sp_")

    other = app.test_client()
    session = other.get(
        "/api/v2/auth/session", headers={"Authorization": "Bearer %s" % token}
    ).get_json()["data"]
    assert session["authenticated"] is True
    assert session["user"]["username"] == "alice"


def test_token_scopes_limit_what_a_token_can_do(client):
    """令牌只能做它声明的范围：upload 不能读，read 不能上传，write 才管改动。"""
    register(client)
    csrf = login(client)

    def issue(scopes):
        response = client.post(
            "/api/v2/auth/tokens",
            json={"name": "scoped", "scopes": scopes},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 201
        return {"Authorization": "Bearer %s" % response.get_json()["data"]["token"]}

    upload_only = issue(["upload"])
    assert client.get("/api/v2/albums", headers=upload_only).status_code == 403
    created = client.post(
        "/api/v2/uploads",
        data={"file": (io.BytesIO(b"scoped"), "a.png")},
        content_type="multipart/form-data",
        headers=upload_only,
    )
    assert created.status_code == 201

    read_only = issue(["read"])
    assert client.get("/api/v2/albums", headers=read_only).status_code == 200
    denied = client.post(
        "/api/v2/uploads",
        data={"file": (io.BytesIO(b"scoped"), "b.png")},
        content_type="multipart/form-data",
        headers=read_only,
    )
    assert denied.status_code == 403
    assert denied.get_json()["code"] == "FORBIDDEN"

    #: 改相册需要 write。
    assert client.post(
        "/api/v2/albums", json={"name": "x"}, headers=read_only
    ).status_code == 403


def test_token_scope_validation(client):
    register(client)
    csrf = login(client)
    headers = {"X-CSRF-Token": csrf}

    #: 未声明范围时给默认集合（read/upload/write，不含 admin）。
    default = client.post("/api/v2/auth/tokens", json={}, headers=headers)
    assert default.status_code == 201
    listed = client.get("/api/v2/auth/tokens").get_json()["data"]["items"]
    assert listed[0]["scopes"] == ["read", "upload", "write"]

    assert client.post(
        "/api/v2/auth/tokens", json={"scopes": ["root"]}, headers=headers
    ).status_code == 400
    #: admin 范围只对管理员开放。
    assert client.post(
        "/api/v2/auth/tokens", json={"scopes": ["admin"]}, headers=headers
    ).status_code == 403


def test_password_reset_requires_a_verified_email(client):
    register(client)
    response = client.post(
        "/api/v2/auth/password/forgot", json={"email": "alice@example.com"}
    )
    assert response.status_code == 202
    #: 注册时邮箱未验证，不会签发重置令牌。
    assert "reset_token" not in response.get_json()["data"]


def test_password_reset_flow(app, client):
    register(client)
    with app.app_context():
        user = User.get(User.username == "alice")
        user.email_verified = True
        user.save(only=[User.email_verified])

    response = client.post(
        "/api/v2/auth/password/forgot", json={"email": "alice@example.com"}
    )
    assert response.status_code == 202
    reset_token = response.get_json()["data"]["reset_token"]

    response = client.post(
        "/api/v2/auth/password/reset",
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
        "/api/v2/auth/password",
        json={"old_password": "secret123", "new_password": "newsecret123"},
        headers={"X-CSRF-Token": second_csrf},
    )
    assert response.status_code == 200

    assert first.get("/api/v2/auth/session").get_json()["data"]["authenticated"] is False
    assert second.get("/api/v2/auth/session").get_json()["data"]["authenticated"] is True


def test_update_profile(client):
    register(client)
    csrf = login(client)

    response = client.put(
        "/api/v2/auth/profile",
        json={"nickname": "爱丽丝", "email": "alice2@example.com", "avatar": "/a.png"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.get_json()
    user = response.get_json()["data"]["user"]
    assert user["nickname"] == "爱丽丝"
    assert user["email"] == "alice2@example.com"
    assert user["avatar"] == "/a.png"
    assert user["username"] == "alice"

    session = client.get("/api/v2/auth/session").get_json()["data"]
    assert session["user"]["nickname"] == "爱丽丝"


def test_update_profile_rejects_taken_email(client):
    register(client)
    client.post("/api/v2/auth/logout")
    register(client, username="bobby", email="bob@example.com")

    csrf = login(client, username="bobby")
    response = client.put(
        "/api/v2/auth/profile",
        json={"email": "alice@example.com"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 409
    assert response.get_json()["code"] == "CONFLICT"

def test_upload_avatar_stores_the_image_in_the_default_album(app, client):
    register(client)
    csrf = login(client)

    response = client.post(
        "/api/v2/auth/avatar",
        data={"file": (io.BytesIO(b"cropped"), "avatar.png")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201, response.get_json()
    data = response.get_json()["data"]
    assert data["avatar"].startswith("/raw/")
    assert data["user"]["avatar"] == data["avatar"]

    with app.app_context():
        user = User.get(User.username == "alice")
        assert user.avatar == data["avatar"]
        album = default_album(user)
        sha = data["avatar"].rsplit("/", 1)[-1]
        image = Image.get(Image.sha == sha)
        assert image.album_id == album.id


def test_upload_avatar_requires_login(client):
    response = client.post(
        "/api/v2/auth/avatar",
        data={"file": (io.BytesIO(b"x"), "avatar.png")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 401


def test_email_verification_round_trip(app, client):
    assert register(client).status_code == 201
    csrf = login(client)

    #: 注册时存下了邮箱，但默认未验证。
    session = client.get("/api/v2/auth/session").get_json()["data"]
    assert session["user"]["email"] == USER["email"]
    assert session["user"]["email_verified"] is False

    sent = client.post("/api/v2/auth/email/verify", headers={"X-CSRF-Token": csrf})
    assert sent.status_code == 202
    token = sent.get_json()["data"]["verify_token"]

    confirmed = client.post(
        "/api/v2/auth/email/confirm",
        json={"token": token},
        headers={"X-CSRF-Token": csrf},
    )
    assert confirmed.status_code == 200
    assert confirmed.get_json()["data"]["user"]["email_verified"] is True

    with app.app_context():
        assert User.get(User.username == "alice").email_verified is True

    #: 已验证的地址不再重复发送。
    again = client.post("/api/v2/auth/email/verify", headers={"X-CSRF-Token": csrf})
    assert again.status_code == 409


def test_changing_email_resets_verification(app, client):
    register(client)
    csrf = login(client)
    token = (
        client.post("/api/v2/auth/email/verify", headers={"X-CSRF-Token": csrf})
        .get_json()["data"]["verify_token"]
    )
    client.post(
        "/api/v2/auth/email/confirm",
        json={"token": token},
        headers={"X-CSRF-Token": csrf},
    )

    updated = client.put(
        "/api/v2/auth/profile",
        json={"email": "new@example.com"},
        headers={"X-CSRF-Token": csrf},
    )
    assert updated.get_json()["data"]["user"]["email_verified"] is False

    #: 旧地址签发的令牌不能给新地址背书。
    stale = client.post(
        "/api/v2/auth/email/confirm",
        json={"token": token},
        headers={"X-CSRF-Token": csrf},
    )
    assert stale.status_code == 400
