# -*- coding: utf-8 -*-
"""Share snippets: v1-compatible HTML / Markdown / rST templates."""

import io

from sapic.libs.images import share_templates

USER = {
    "username": "heidi",
    "password": "secret123",
    "email": "heidi@example.com",
}


def test_image_templates_match_v1():
    tpl = share_templates(
        "https://img.example.com/a.png", filename="a.png", title="海边"
    )

    assert tpl["URL"] == "https://img.example.com/a.png"
    assert tpl["HTML"] == (
        "<img src='https://img.example.com/a.png' title='海边' alt='a.png'>"
    )
    assert tpl["Markdown"] == "![a.png](https://img.example.com/a.png)"
    assert tpl["rST"] == ".. image:: https://img.example.com/a.png"


def test_video_templates_use_figure_frame():
    tpl = share_templates(
        "https://img.example.com/a.mp4", filename="a.mp4", title="clip", is_video=True
    )

    assert tpl["HTML"] == (
        "<video src='https://img.example.com/a.mp4' title='clip' controls></video>"
    )
    assert tpl["Markdown"].startswith("<figure><iframe src='")
    assert tpl["rST"].startswith(".. raw:: html\n\n\t<figure>")


def test_missing_title_and_filename_are_tolerated():
    tpl = share_templates("/raw/sha1.1.abc")
    assert "alt=''" in tpl["HTML"]
    assert tpl["Markdown"].startswith("![](")


def signin(client):
    client.post("/api/v2/auth/register", json=USER)
    response = client.post(
        "/api/v2/auth/login",
        json={"username": USER["username"], "password": USER["password"]},
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]["csrf"]


def test_detail_endpoint_returns_templates(client):
    csrf = signin(client)
    upload = client.post(
        "/api/v2/upload",
        data={"file": (io.BytesIO(b"fake-image-bytes"), "photo.png")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )
    assert upload.status_code in (200, 201), upload.get_json()
    sha = upload.get_json()["data"]["image"]["sha"]

    body = client.get(f"/api/v2/images/{sha}").get_json()
    tpl = body["data"]["image"]["tpl"]
    assert set(tpl) == {"URL", "HTML", "Markdown", "rST"}
    assert sha in tpl["URL"]
    assert tpl["Markdown"] == "![photo.png](%s)" % tpl["URL"]
