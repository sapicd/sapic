# -*- coding: utf-8 -*-
import io
import re
from urllib.error import HTTPError, URLError

import pytest

from sapic.basis.errors import ApiError
from sapic.libs import images
from sapic.libs.settings import set_setting
from sapic.models import Image, ImageBackend, User


def register_and_login(client):
    client.post(
        "/api/v2/auth/register",
        json={
            "username": "alice",
            "password": "secret123",
            "email": "alice@example.com",
        },
    )
    response = client.post(
        "/api/v2/auth/login",
        json={"username": "alice", "password": "secret123"},
    )
    return response.get_json()["data"]["csrf"]


def upload(client, csrf=None, filename="photo.png", content=b"fake-image-bytes", **form):
    headers = {"X-CSRF-Token": csrf} if csrf else {}
    data = {"file": (io.BytesIO(content), filename)}
    data.update(form)
    return client.post(
        "/api/v2/upload",
        data=data,
        content_type="multipart/form-data",
        headers=headers,
    )


def test_upload_and_read(app, client, tmp_path):
    csrf = register_and_login(client)
    response = upload(client, csrf)
    assert response.status_code == 201, response.get_json()

    image = response.get_json()["data"]["image"]
    assert image["sha"].startswith("sha1.")
    assert image["src"].endswith("/raw/%s" % image["sha"])

    with app.app_context():
        row = Image.get(Image.sha == image["sha"])
        assert row.size == len(b"fake-image-bytes")
        replica = ImageBackend.get(ImageBackend.image == row)
        assert replica.state == "ok"
        assert replica.is_primary is True

    response = client.get(image["src"])
    assert response.status_code == 200
    assert response.data == b"fake-image-bytes"


def test_listing_never_leaks_other_peoples_images(app, client):
    """图片列表是个人图库：别人公开相册里的图片不该出现，即使匿名也一样。"""
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]

    bobby = app.test_client()
    bobby.post(
        "/api/v2/auth/register",
        json={
            "username": "bobby",
            "password": "secret123",
            "email": "bobby@example.com",
        },
    )
    bobby.post(
        "/api/v2/auth/login",
        json={"username": "bobby", "password": "secret123"},
    )
    assert bobby.get("/api/v2/images").get_json()["data"]["items"] == []
    #: 列表要求登录，匿名直接 401，连空列表都不给。
    assert app.test_client().get("/api/v2/images").status_code == 401
    #: 知道地址仍然能看（公开图就是外链），只是不再出现在别人的列表里。
    assert bobby.get("/raw/%s" % sha).status_code == 200
    #: 详情页要能判断编辑权限，别人点进来只读。
    assert bobby.get("/api/v2/images/%s" % sha).get_json()["data"]["image"][
        "can_edit"
    ] is False
    assert client.get("/api/v2/images/%s" % sha).get_json()["data"]["image"][
        "can_edit"
    ] is True


def test_admin_gallery_defaults_to_own_images(app, client):
    """管理员默认也只看自己的图库，全站图片要用 scope=all 显式打开。"""
    csrf = register_and_login(client)
    mine = upload(client, csrf).get_json()["data"]["image"]["sha"]

    bobby = app.test_client()
    bobby.post(
        "/api/v2/auth/register",
        json={
            "username": "bobby",
            "password": "secret123",
            "email": "bobby@example.com",
        },
    )
    bobby_csrf = bobby.post(
        "/api/v2/auth/login",
        json={"username": "bobby", "password": "secret123"},
    ).get_json()["data"]["csrf"]
    other = upload(bobby, bobby_csrf).get_json()["data"]["image"]["sha"]

    with app.app_context():
        User.update(is_admin=True).where(User.username == "alice").execute()

    #: 默认仍是个人图库：别人的图片不会因为自己是管理员就自动冒出来。
    default = client.get("/api/v2/images").get_json()["data"]["items"]
    assert [item["sha"] for item in default] == [mine]

    #: 点了「显示全站图片」（scope=all）才给全量。
    everyone = client.get("/api/v2/images?scope=all").get_json()["data"]["items"]
    assert {item["sha"] for item in everyone} == {mine, other}

    #: 非管理员要不到全站视图，scope 也只接受约定的值。
    assert bobby.get("/api/v2/images?scope=all").status_code == 403
    assert client.get("/api/v2/images?scope=someone").status_code == 400


def test_admin_all_scope_hides_private_images(app, client):
    """全站视图只放大到公开图：别人的私有相册不能被管理员列表兜底暴露。"""
    csrf = register_and_login(client)
    alice_public = upload(client, csrf).get_json()["data"]["image"]["sha"]

    #: alice 自己的私有图：个人图库看得到，全站视图不该出现。
    alice_private_album = client.post(
        "/api/v2/albums",
        json={"name": "秘密", "visibility": "private"},
        headers={"X-CSRF-Token": csrf},
    ).get_json()["data"]["album"]
    alice_private = upload(
        client, csrf, album_id=alice_private_album["id"]
    ).get_json()["data"]["image"]["sha"]

    bobby = app.test_client()
    bobby.post(
        "/api/v2/auth/register",
        json={
            "username": "bobby",
            "password": "secret123",
            "email": "bobby@example.com",
        },
    )
    bobby_csrf = bobby.post(
        "/api/v2/auth/login",
        json={"username": "bobby", "password": "secret123"},
    ).get_json()["data"]["csrf"]
    bobby_public = upload(bobby, bobby_csrf).get_json()["data"]["image"]["sha"]
    bobby_private_album = bobby.post(
        "/api/v2/albums",
        json={"name": "私密", "visibility": "private"},
        headers={"X-CSRF-Token": bobby_csrf},
    ).get_json()["data"]["album"]
    bobby_private = upload(
        bobby, bobby_csrf, album_id=bobby_private_album["id"]
    ).get_json()["data"]["image"]["sha"]
    assert bobby_private != bobby_public

    with app.app_context():
        User.update(is_admin=True).where(User.username == "alice").execute()

    #: 个人图库：自己的公开图与私有图都在。
    mine = client.get("/api/v2/images").get_json()["data"]["items"]
    assert {item["sha"] for item in mine} == {alice_public, alice_private}

    #: 全站视图：只多出 bobby 的公开图，两张私有图都不出现。
    everyone = client.get("/api/v2/images?scope=all").get_json()["data"]["items"]
    assert {item["sha"] for item in everyone} == {alice_public, bobby_public}


def test_system_album_and_anonymous_images_are_admin_only(app, client):
    """匿名图落在系统相册：相册条目与图片列表都只对管理员可见。"""
    set_setting("allow_anonymous_upload", True)
    anonymous = upload(app.test_client())
    assert anonymous.status_code == 201, anonymous.get_json()
    sha = anonymous.get_json()["data"]["image"]["sha"]

    csrf = register_and_login(client)
    with app.app_context():
        User.update(is_admin=True).where(User.username == "alice").execute()

    #: 普通用户（bobby）拿到的相册列表里没有系统相册。
    bobby = app.test_client()
    bobby.post(
        "/api/v2/auth/register",
        json={
            "username": "bobby",
            "password": "secret123",
            "email": "bobby@example.com",
        },
    )
    bobby.post(
        "/api/v2/auth/login",
        json={"username": "bobby", "password": "secret123"},
    )
    bobby_albums = bobby.get("/api/v2/albums").get_json()["data"]["items"]
    assert not [album for album in bobby_albums if album["is_system"]]

    #: 管理员能拿到 role=system 的那条，用它筛匿名图。
    admin_albums = client.get("/api/v2/albums").get_json()["data"]["items"]
    system = [album for album in admin_albums if album["is_system"]]
    assert len(system) == 1 and system[0]["role"] == "system"
    system_id = system[0]["id"]

    #: 匿名图不在任何普通用户的图库里。
    assert bobby.get("/api/v2/images").get_json()["data"]["items"] == []
    assert client.get("/api/v2/images").get_json()["data"]["items"] == []
    #: 即便猜到系统相册 id，也筛不出东西（列表起点仍是自己的图库）。
    assert (
        bobby.get("/api/v2/images?album_id=%s" % system_id).get_json()["data"]["items"]
        == []
    )

    #: 管理员的全站视图能看到匿名图（系统相册是公开相册），也能按它筛选。
    everyone = client.get("/api/v2/images?scope=all").get_json()["data"]["items"]
    assert sha in {item["sha"] for item in everyone}
    only_system = client.get(
        "/api/v2/images?scope=all&album_id=%s" % system_id
    ).get_json()["data"]["items"]
    assert {item["sha"] for item in only_system} == {sha}

    #: 相册页点进来只带 album_id（默认 scope=mine），管理员也要能筛出匿名图，
    #: 否则系统相册条目上的张数与点进去的空列表自相矛盾。
    from_album_page = client.get(
        "/api/v2/images?album_id=%s" % system_id
    ).get_json()["data"]["items"]
    assert {item["sha"] for item in from_album_page} == {sha}

    #: 匿名图本身仍是公开直链（图床语义），只是不出现在别人的列表里。
    assert app.test_client().get("/raw/%s" % sha).status_code == 200

    #: 系统相册没有 owner（`owner_id` 为 NULL），改不了，所以匿名图不会
    #: 因为「相册被设成私有」而从全站视图里消失。
    assert (
        client.patch(
            "/api/v2/albums/%s" % system_id,
            json={"visibility": "private"},
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 404
    )


def test_image_listing_and_update(app, client):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]

    listing = client.get("/api/v2/images").get_json()["data"]
    assert listing["items"][0]["sha"] == sha
    assert listing["has_more"] is False

    response = client.patch(
        "/api/v2/images/%s" % sha,
        json={"title": "new title"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["image"]["title"] == "new title"


def test_image_visibility_rejects_shared(app, client):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]

    #: 共享是按相册授权的，单图覆盖只接受 public / private。
    response = client.patch(
        "/api/v2/images/%s" % sha,
        json={"visibility": "shared"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "PARAM_ERROR"

    response = client.patch(
        "/api/v2/images/%s" % sha,
        json={"visibility": "private"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["image"]["visibility"] == "private"


def test_delete_image(app, client):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]

    response = client.delete(
        "/api/v2/images/%s" % sha, headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 200
    assert client.get("/raw/%s" % sha).status_code == 404

    with app.app_context():
        assert Image.get(Image.sha == sha).status == "deleted"
        assert ImageBackend.select().where(
            ImageBackend.image == Image.get(Image.sha == sha)
        ).count() == 0


def test_upload_rejects_unknown_suffix(client):
    csrf = register_and_login(client)
    response = upload(client, csrf, filename="shell.php")
    assert response.status_code == 400
    assert response.get_json()["code"] == "PARAM_ERROR"


def test_same_name_uploads_do_not_overwrite(app, client):
    csrf = register_and_login(client)

    first = upload(client, csrf, content=b"first").get_json()["data"]["image"]
    second = upload(client, csrf, content=b"second").get_json()["data"]["image"]

    assert first["sha"] != second["sha"]
    assert client.get("/raw/%s" % first["sha"]).data == b"first"
    assert client.get("/raw/%s" % second["sha"]).data == b"second"

    with app.app_context():
        keys = [row.object_key for row in ImageBackend.select()]
        assert len(keys) == 2
        assert len(set(keys)) == 2
        #: 展示用的文件名保持原样，只有存储 key 带唯一后缀。
        assert Image.get(Image.sha == first["sha"]).filename == "photo.png"


def test_upload_generates_a_name_when_it_cannot_be_read(app, client):
    csrf = register_and_login(client)
    #: 纯中文名会被 secure_filename 清空，按时间戳+随机串兜底，后缀必须保住。
    response = upload(client, csrf, filename="截图.png")
    assert response.status_code == 201, response.get_json()

    image = response.get_json()["data"]["image"]
    assert re.match(r"^\d{14}[0-9a-f]{6}\.png$", image["filename"])

    with app.app_context():
        replica = ImageBackend.get(
            ImageBackend.image == Image.get(Image.sha == image["sha"])
        )
        key = replica.object_key.rsplit("/", 1)[-1]
        assert key.startswith(image["filename"].rsplit(".", 1)[0])


def test_upload_from_url(app, client, monkeypatch):
    csrf = register_and_login(client)
    monkeypatch.setattr(
        "sapic.views.uploads.download_image",
        lambda url, max_bytes: (b"remote-bytes", "remote.png", "image/png"),
    )

    response = client.post(
        "/api/v2/upload",
        data={"url": "https://example.com/remote.png"},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201, response.get_json()

    image = response.get_json()["data"]["image"]
    assert image["filename"] == "remote.png"
    assert client.get(image["src"]).data == b"remote-bytes"


def test_upload_from_url_rejects_unsupported_url(client):
    csrf = register_and_login(client)
    headers = {"X-CSRF-Token": csrf}

    response = client.post(
        "/api/v2/upload",
        data={"url": "file:///etc/passwd"},
        content_type="multipart/form-data",
        headers=headers,
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "PARAM_ERROR"

    #: 内网/环回地址在建立连接前就被拒绝，避免 SSRF。
    response = client.post(
        "/api/v2/upload",
        data={"url": "http://127.0.0.1/photo.png"},
        content_type="multipart/form-data",
        headers=headers,
    )
    assert response.status_code == 403


def test_anonymous_upload_disabled_by_default(client):
    response = upload(client)
    assert response.status_code == 403
    assert response.get_json()["code"] == "FORBIDDEN"


def test_anonymous_upload_when_enabled(app, client):
    with app.app_context():
        set_setting("allow_anonymous_upload", True)

    response = upload(client)
    assert response.status_code == 201, response.get_json()
    image = response.get_json()["data"]["image"]

    with app.app_context():
        row = Image.get(Image.sha == image["sha"])
        assert row.owner_id is None
    assert client.get(image["src"]).status_code == 200


def test_image_listing_filters_by_album(client):
    csrf = register_and_login(client)

    album = client.post(
        "/api/v2/albums",
        json={"name": "旅行", "visibility": "public"},
        headers={"X-CSRF-Token": csrf},
    ).get_json()["data"]["album"]

    inside = upload(client, csrf).get_json()["data"]["image"]
    outside = upload(client, csrf, "other.png").get_json()["data"]["image"]
    client.patch(
        "/api/v2/images/%s" % inside["sha"],
        json={"album_id": album["id"]},
        headers={"X-CSRF-Token": csrf},
    )

    listing = client.get(
        "/api/v2/images", query_string={"album_id": album["id"]}
    ).get_json()["data"]
    shas = [item["sha"] for item in listing["items"]]
    assert shas == [inside["sha"]]
    assert outside["sha"] not in shas


def test_public_image_hides_its_private_album(app, client):
    """单图覆盖成公开时，别人不该顺带看到它所在私有相册的名字。"""
    csrf = register_and_login(client)
    album = client.post(
        "/api/v2/albums",
        json={"name": "私房", "visibility": "private"},
        headers={"X-CSRF-Token": csrf},
    ).get_json()["data"]["album"]
    image = upload(client, csrf).get_json()["data"]["image"]
    for payload in ({"album_id": album["id"]}, {"visibility": "public"}):
        client.patch(
            "/api/v2/images/%s" % image["sha"],
            json=payload,
            headers={"X-CSRF-Token": csrf},
        )

    anonymous = app.test_client()
    detail = anonymous.get("/api/v2/images/%s" % image["sha"]).get_json()["data"]
    assert detail["image"]["album"] is None
    assert anonymous.get("/raw/%s" % image["sha"]).status_code == 200

    #: 作者本人仍然拿得到相册信息。
    own = client.get("/api/v2/images/%s" % image["sha"]).get_json()["data"]
    assert own["image"]["album"]["name"] == "私房"


def test_image_cannot_be_detached_from_its_album(client):
    """图片必须留在相册里，否则会跌回 public 变成匿名可读。"""
    csrf = register_and_login(client)
    uploaded = upload(client, csrf).get_json()["data"]["image"]

    response = client.patch(
        "/api/v2/images/%s" % uploaded["sha"],
        json={"album_id": None},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "PARAM_ERROR"


def test_image_payload_carries_its_album(client):
    csrf = register_and_login(client)
    uploaded = upload(client, csrf).get_json()["data"]["image"]

    detail = client.get("/api/v2/images/%s" % uploaded["sha"]).get_json()["data"]
    assert detail["image"]["album"]["id"] == uploaded["album_id"]
    assert detail["image"]["album"]["name"]

    listing = client.get("/api/v2/images").get_json()["data"]["items"]
    item = next(entry for entry in listing if entry["sha"] == uploaded["sha"])
    assert item["album"]["id"] == uploaded["album_id"]


def test_image_tags_are_normalized_and_filterable(client):
    csrf = register_and_login(client)
    tagged = upload(client, csrf).get_json()["data"]["image"]
    other = upload(client, csrf, "other.png").get_json()["data"]["image"]

    response = client.patch(
        "/api/v2/images/%s" % tagged["sha"],
        json={"tags": ["旅行", " 旅行 ", "", "海边"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["image"]["tags"] == ["旅行", "海边"]

    detail = client.get("/api/v2/images/%s" % tagged["sha"]).get_json()["data"]
    assert detail["image"]["tags"] == ["旅行", "海边"]

    listing = client.get(
        "/api/v2/images", query_string={"tag": "旅行"}
    ).get_json()["data"]
    shas = [item["sha"] for item in listing["items"]]
    assert shas == [tagged["sha"]]
    assert other["sha"] not in shas


def test_image_tags_reject_oversized_input(client):
    csrf = register_and_login(client)
    uploaded = upload(client, csrf).get_json()["data"]["image"]

    too_many = ["t%d" % index for index in range(11)]
    response = client.patch(
        "/api/v2/images/%s" % uploaded["sha"],
        json={"tags": too_many},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "PARAM_ERROR"

    response = client.patch(
        "/api/v2/images/%s" % uploaded["sha"],
        json={"tags": ["x" * 33]},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 400


def test_image_listing_supports_page_numbers(client):
    """页码模式给前端的页码器用：total、has_more 与跨页顺序都要对。"""
    csrf = register_and_login(client)
    shas = [
        upload(client, csrf, filename="p%d.png" % index)
        .get_json()["data"]["image"]["sha"]
        for index in range(5)
    ]

    first = client.get("/api/v2/images?page=1&page_size=2").get_json()["data"]
    assert first["total"] == 5
    assert first["page"] == 1
    assert first["page_size"] == 2
    assert first["has_more"] is True
    assert len(first["items"]) == 2

    second = client.get("/api/v2/images?page=2&page_size=2").get_json()["data"]
    last = client.get("/api/v2/images?page=3&page_size=2").get_json()["data"]
    assert last["has_more"] is False
    assert len(last["items"]) == 1

    #: 三页拼起来不重不漏；同一秒上传时靠 id 兜底排序，翻页顺序必须稳定。
    seen = [item["sha"] for item in first["items"] + second["items"] + last["items"]]
    assert sorted(seen) == sorted(shas)


def test_image_listing_keeps_cursor_mode_without_page(client):
    """不带 ``page`` 仍是游标分页，老客户端与脚本不受影响。"""
    csrf = register_and_login(client)
    upload(client, csrf)

    data = client.get("/api/v2/images?limit=1").get_json()["data"]
    assert "next_cursor" in data
    assert "total" not in data


class _FakeOpener:
    """Stands in for ``urlopen``, recording which route each attempt used."""

    def __init__(self, proxy, attempts, direct_fails):
        self.proxy = proxy
        self.attempts = attempts
        self.direct_fails = direct_fails

    def open(self, request, timeout=None):
        self.attempts.append(self.proxy)
        if not self.proxy and self.direct_fails:
            raise URLError("direct connection refused")
        return "response"


def _opener_factory(attempts, direct_fails=True):
    """Build an ``images.build_opener`` replacement reading the ProxyHandler."""

    def fake_build(*handlers):
        proxy = handlers[1].proxies.get("https", "")
        return _FakeOpener(proxy, attempts, direct_fails)

    return fake_build


def test_url_fetch_uses_the_proxy_only_as_a_fallback(app, monkeypatch):
    """代理是兜底：直连失败才改走代理，不是默认通道。"""
    attempts = []
    monkeypatch.setattr(images, "build_opener", _opener_factory(attempts))

    with app.app_context():
        set_setting("upload_fetch_proxy", "http://127.0.0.1:7890")
        #: 用 IP 字面量，两条路径都不依赖真实 DNS。
        assert images.open_remote("https://1.1.1.1/photo.png") == "response"

    assert attempts == ["", "http://127.0.0.1:7890"]


def test_url_fetch_skips_the_proxy_when_direct_works(app, monkeypatch):
    """能直连的源不绕代理，国内图不会被拖慢。"""
    attempts = []
    monkeypatch.setattr(
        images, "build_opener", _opener_factory(attempts, direct_fails=False)
    )

    with app.app_context():
        set_setting("upload_fetch_proxy", "http://127.0.0.1:7890")
        assert images.open_remote("https://1.1.1.1/photo.png") == "response"

    assert attempts == [""]


def test_unresolvable_host_falls_back_to_the_proxy(app, monkeypatch):
    """本地解析不了（外网域名常见）也算直连抓不到，交给代理兜底。"""
    attempts = []
    monkeypatch.setattr(images, "build_opener", _opener_factory(attempts))

    def unresolvable(host, port, *args, **kwargs):
        raise OSError("name or service not known")

    monkeypatch.setattr(images.socket, "getaddrinfo", unresolvable)

    with app.app_context():
        set_setting("upload_fetch_proxy", "http://127.0.0.1:7890")
        assert images.open_remote("https://pbs.example.com/a.png") == "response"

    #: 解析失败时连直连请求都没发出去，第一次尝试就是代理。
    assert attempts == ["http://127.0.0.1:7890"]


def test_proxied_fetch_still_rejects_private_literals(monkeypatch):
    """走代理时内网字面量仍在本地拦住，不交给代理去连。"""
    attempts = []
    monkeypatch.setattr(images, "build_opener", _opener_factory(attempts))

    with pytest.raises(ApiError) as exc:
        images._open_once(
            "http://10.0.0.1/a.png", 10, None, False, "http://127.0.0.1:7890"
        )

    assert exc.value.status_code == 403
    assert attempts == []


def test_backend_url_never_uses_the_proxy(app, monkeypatch):
    """存储后端的内部地址（allow_private）留在内网，不经过第三方代理。"""
    attempts = []
    monkeypatch.setattr(
        images, "build_opener", _opener_factory(attempts, direct_fails=False)
    )

    with app.app_context():
        set_setting("upload_fetch_proxy", "http://127.0.0.1:7890")
        response = images.open_remote(
            "http://127.0.0.1:9000/bucket/a.png", allow_private=True
        )

    assert response == "response"
    assert attempts == [""]


class _FakeRemoteResponse:
    """Minimal stand-in for the streamed response of a URL fetch."""

    def __init__(self, mime="image/jpeg", body=b"remote-bytes", broken=False):
        self.headers = _FakeHeaders(mime)
        self._body = body
        self._broken = broken
        self.closed = False

    def geturl(self):
        return ""

    def read(self, size=-1):
        if self._broken:
            raise ConnectionResetError("connection reset by peer")
        body, self._body = self._body, b""
        return body

    def close(self):
        self.closed = True


class _FakeHeaders:
    def __init__(self, mime):
        self._mime = mime

    def get_content_type(self):
        return self._mime

    def get(self, name, default=None):
        return default


def _blocking_opener_factory(
    attempts, direct_status=None, direct_mime="image/jpeg", direct_broken=False
):
    """Direct attempt answers with an HTTP error or an unusable payload."""

    class Opener:
        def __init__(self, proxy):
            self.proxy = proxy

        def open(self, request, timeout=None):
            attempts.append(self.proxy)
            if not self.proxy:
                if direct_status:
                    raise HTTPError(
                        request.full_url, direct_status, "blocked", {}, io.BytesIO(b"")
                    )
                return _FakeRemoteResponse(direct_mime, broken=direct_broken)
            return _FakeRemoteResponse()

    def fake_build(*handlers):
        return Opener(handlers[1].proxies.get("https", ""))

    return fake_build


def test_http_error_on_the_direct_fetch_still_tries_the_proxy(app, monkeypatch):
    """被挡时常见的是边缘节点直接回 403，而不是连不上；代理同样要兜底。"""
    attempts = []
    monkeypatch.setattr(
        images, "build_opener", _blocking_opener_factory(attempts, direct_status=403)
    )

    with app.app_context():
        set_setting("upload_fetch_proxy", "http://127.0.0.1:7890")
        stream, name, mime = images.download_image("https://1.1.1.1/a.jpg", 1024)

    assert attempts == ["", "http://127.0.0.1:7890"]
    assert stream == b"remote-bytes"
    assert (name, mime) == ("a.jpg", "image/jpeg")


def test_interstitial_page_on_the_direct_fetch_tries_the_proxy(app, monkeypatch):
    """200 + text/html 的拦截页也算直连没抓到，换代理再试一次。"""
    attempts = []
    monkeypatch.setattr(
        images,
        "build_opener",
        _blocking_opener_factory(attempts, direct_mime="text/html"),
    )

    with app.app_context():
        set_setting("upload_fetch_proxy", "http://127.0.0.1:7890")
        stream, _, mime = images.download_image("https://1.1.1.1/a.jpg", 1024)

    assert attempts == ["", "http://127.0.0.1:7890"]
    assert stream == b"remote-bytes"
    assert mime == "image/jpeg"


def test_truncated_body_on_the_direct_fetch_retries_via_proxy(app, monkeypatch):
    """拿到 200 头但 body 断流（海外图很常见）同样要换代理，否则等于白等。"""
    attempts = []
    monkeypatch.setattr(
        images,
        "build_opener",
        _blocking_opener_factory(attempts, direct_broken=True),
    )

    with app.app_context():
        set_setting("upload_fetch_proxy", "http://127.0.0.1:7890")
        stream, _, mime = images.download_image("https://1.1.1.1/a.jpg", 1024)

    assert attempts == ["", "http://127.0.0.1:7890"]
    assert stream == b"remote-bytes"
    assert mime == "image/jpeg"


def test_fetch_error_message_keeps_the_direct_cause(app, monkeypatch):
    """没配代理时错误里带上原因，运维才知道是 403 还是连不上。"""
    attempts = []
    monkeypatch.setattr(
        images, "build_opener", _blocking_opener_factory(attempts, direct_status=403)
    )

    with app.app_context():
        with pytest.raises(ApiError) as exc:
            images.download_image("https://1.1.1.1/a.jpg", 1024)

    assert exc.value.message == "remote fetch failed: http 403"
    assert attempts == [""]
