# -*- coding: utf-8 -*-
from sapic.libs.settings import set_setting


def test_site_metadata_is_public(client):
    response = client.get("/api/v1/site")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["name"] == "sapic"
    assert data["background"] == ""
    assert data["allow_anonymous_upload"] is False


def test_site_metadata_reads_settings(app, client):
    with app.app_context():
        set_setting("site_name", "图床")
        set_setting("site_background", "https://example.com/bg.jpg")

    data = client.get("/api/v1/site").get_json()["data"]
    assert data["name"] == "图床"
    assert data["background"] == "https://example.com/bg.jpg"
