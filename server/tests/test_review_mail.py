# -*- coding: utf-8 -*-
"""Registration review: rejection reason and the notification mail."""

import pytest

from sapic.libs import users as users_lib
from sapic.libs.users import create_user
from sapic.models import User
from sapic.models.user import STATUS_DISABLED, STATUS_PENDING, STATUS_REJECTED

ADMIN = {
    "username": "frank",
    "password": "secret123",
    "email": "frank@example.com",
}

APPLICANT = {
    "username": "grace",
    "password": "secret123",
    "email": "grace@example.com",
}


@pytest.fixture
def sent(monkeypatch):
    """Collect ``send_mail`` calls instead of touching SMTP."""
    calls = []

    def fake_send(to, subject, body):
        calls.append({"to": to, "subject": subject, "body": body})
        return True

    monkeypatch.setattr(users_lib, "send_mail", fake_send)
    return calls


def signin_admin(client, app):
    client.post("/api/v2/auth/register", json=ADMIN)
    response = client.post(
        "/api/v2/auth/login",
        json={"username": ADMIN["username"], "password": ADMIN["password"]},
    )
    assert response.status_code == 200, response.get_json()
    with app.app_context():
        User.update(is_admin=True).where(User.username == ADMIN["username"]).execute()
    return response.get_json()["data"]["csrf"]


def pending_applicant(app, verified=True):
    with app.app_context():
        user = create_user(
            APPLICANT["username"],
            APPLICANT["password"],
            email=APPLICANT["email"],
            status=STATUS_PENDING,
        )
        user.email_verified = verified
        user.save(only=[User.email_verified])
        return user.id


def patch_user(client, csrf, user_id, payload):
    return client.patch(
        f"/api/v2/users/{user_id}", json=payload, headers={"X-CSRF-Token": csrf}
    )


def test_approval_sends_mail_and_clears_reason(app, client, sent):
    csrf = signin_admin(client, app)
    user_id = pending_applicant(app)

    response = patch_user(client, csrf, user_id, {"status": 1})
    assert response.status_code == 200, response.get_json()
    assert len(sent) == 1
    assert sent[0]["to"] == APPLICANT["email"]
    assert "通过" in sent[0]["subject"]

    with app.app_context():
        user = User.get_by_id(user_id)
        assert user.status == 1
        assert user.status_reason is None


def test_rejection_keeps_reason_and_mails_it(app, client, sent):
    csrf = signin_admin(client, app)
    user_id = pending_applicant(app)

    response = patch_user(
        client, csrf, user_id, {"status": STATUS_REJECTED, "reason": "图片涉嫌违规"}
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["data"]["user"]["status_reason"] == "图片涉嫌违规"
    assert len(sent) == 1
    assert "图片涉嫌违规" in sent[0]["body"]

    with app.app_context():
        assert User.get_by_id(user_id).status_reason == "图片涉嫌违规"


def test_unverified_mailbox_is_not_mailed(app, client, sent):
    csrf = signin_admin(client, app)
    user_id = pending_applicant(app, verified=False)

    patch_user(client, csrf, user_id, {"status": 1})
    assert sent == []


def test_disable_is_not_a_review(app, client, sent):
    csrf = signin_admin(client, app)
    user_id = pending_applicant(app)

    patch_user(client, csrf, user_id, {"status": STATUS_DISABLED})
    assert sent == []


def test_reason_is_cleared_when_accepted_later(app, client, sent):
    csrf = signin_admin(client, app)
    user_id = pending_applicant(app)
    patch_user(client, csrf, user_id, {"status": STATUS_REJECTED, "reason": "重复注册"})

    response = patch_user(client, csrf, user_id, {"status": 1})
    assert response.json["data"]["user"]["status_reason"] == ""
    with app.app_context():
        assert User.get_by_id(user_id).status_reason is None
