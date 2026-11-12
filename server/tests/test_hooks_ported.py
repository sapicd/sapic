# -*- coding: utf-8 -*-
"""The v1 drivers ported to the v2 hook contract."""

from io import BytesIO

import pytest

from sapic.libs import images

DRIVERS = ("up2github", "up2gitee", "up2qiniu", "up2upyun")


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeRequests:
    """Records calls and replies with the queued responses."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def _reply(self, method, url, kwargs):
        self.calls.append((method, url, kwargs))
        if self.responses:
            return self.responses.pop(0)
        return FakeResponse(200, {})

    def put(self, url, **kwargs):
        return self._reply("put", url, kwargs)

    def post(self, url, **kwargs):
        return self._reply("post", url, kwargs)

    def get(self, url, **kwargs):
        return self._reply("get", url, kwargs)

    def delete(self, url, **kwargs):
        return self._reply("delete", url, kwargs)


class StubManager:
    def __init__(self, results):
        self.results = results

    def call(self, funcname, **kwargs):
        assert funcname == "upimg_stream_processor"
        return list(self.results)


def module_of(app, name):
    return app.extensions["hooks"].get(name).module


def test_ported_hooks_are_loaded(app):
    manager = app.extensions["hooks"]
    for name in DRIVERS:
        hook = manager.get(name)
        assert hook.meta["__catalog__"] == "upload"
        assert hook.meta["__state__"] == "disabled"

    processor = manager.get("pic2webp")
    assert processor.meta["__catalog__"] == "processor"
    assert processor.enabled is False


def test_drivers_declare_an_admin_form(app):
    for name in DRIVERS:
        manifest = app.extensions["hooks"].manifest(name)
        keys = [field["key"] for field in manifest["config_schema"]]
        assert "basedir" in keys
        assert [action["name"] for action in manifest["actions"]] == ["ping"]
        assert manifest["slots"] == [
            {"name": "admin.hook_setting", "mode": "declarative"}
        ]


def test_driver_slot_fills_defaults_from_saved_config(app):
    module = module_of(app, "up2github")
    nodes = module.slot_admin_hook_setting(
        context={
            "backend": {
                "config": {"token": "t", "repo": "a/b", "basedir": "img"},
                "in_use": True,
            }
        }
    )

    children = nodes[0]["children"]
    assert children[0]["type"] == "alert"
    fields = {child["key"]: child for child in children if "key" in child}
    assert fields["repo"]["default"] == "a/b"
    assert fields["basedir"]["default"] == "img"
    button = next(child for child in children if child["type"] == "button")
    assert button["action"] == "ping"


def test_github_save_returns_the_object_key(app, monkeypatch):
    module = module_of(app, "up2github")
    fake = FakeRequests(FakeResponse(201, {"content": {"size": 5, "sha": "blob"}}))
    monkeypatch.setattr(module, "requests", fake)

    result = module.upimg_save(
        "photo.png",
        b"bytes",
        "alice/2026",
        backend={"config": {"token": "t", "repo": "a/b", "basedir": "/img/"}},
    )

    assert result["code"] == 0
    assert result["path"] == "img/alice/2026/photo.png"
    assert result["size"] == 5
    assert result["etag"] == "blob"
    #: 没有加速域名时用 jsDelivr 兜底。
    assert result["src"] == (
        "https://cdn.jsdelivr.net/gh/a/b/img/alice/2026/photo.png"
    )
    method, url, kwargs = fake.calls[0]
    assert method == "put"
    assert url.endswith("/repos/a/b/contents/img/alice/2026/photo.png")
    assert kwargs["headers"]["Authorization"] == "token t"


def test_github_save_prefers_the_acceleration_domain(app, monkeypatch):
    module = module_of(app, "up2github")
    fake = FakeRequests(FakeResponse(201, {"content": {"size": 5, "sha": "blob"}}))
    monkeypatch.setattr(module, "requests", fake)

    result = module.upimg_save(
        "photo.png",
        b"bytes",
        "alice/2026",
        backend={
            "config": {
                "token": "t",
                "repo": "a/b",
                "domain": "https://static.example.com/",
            }
        },
    )

    assert result["code"] == 0
    assert result["src"] == "https://static.example.com/alice/2026/photo.png"


def test_github_save_rejects_incomplete_config(app, monkeypatch):
    module = module_of(app, "up2github")
    monkeypatch.setattr(module, "requests", FakeRequests())
    result = module.upimg_save(
        "a.png", b"x", backend={"config": {"repo": "a/b"}}
    )
    assert result["code"] == 1
    assert "parameter error" in result["message"]


def test_github_delete_reuses_the_stored_etag(app, monkeypatch):
    module = module_of(app, "up2github")
    fake = FakeRequests(FakeResponse(200, {}))
    monkeypatch.setattr(module, "requests", fake)

    result = module.upimg_delete(
        "sha1.1.x",
        "",
        "photo.png",
        "",
        {"path": "img/photo.png", "etag": "blob"},
        backend={"config": {"token": "t", "repo": "a/b", "branch": "dev"}},
    )

    assert result["code"] == 0
    method, url, kwargs = fake.calls[0]
    assert method == "delete"
    assert kwargs["json"]["sha"] == "blob"
    assert kwargs["json"]["branch"] == "dev"


def test_gitee_save_sends_the_token_as_a_parameter(app, monkeypatch):
    module = module_of(app, "up2gitee")
    fake = FakeRequests(FakeResponse(201, {"content": {"size": 3, "sha": "xyz"}}))
    monkeypatch.setattr(module, "requests", fake)

    result = module.upimg_save(
        "a.png", b"abc", "", backend={"config": {"token": "tk", "repo": "a/b"}}
    )

    assert result["code"] == 0
    assert result["path"] == "a.png"
    assert fake.calls[0][2]["data"]["access_token"] == "tk"


@pytest.mark.parametrize(
    "name, vendor, attr",
    (("up2qiniu", "qiniu", "Auth"), ("up2upyun", "upyun", "UpYun")),
)
def test_sdk_drivers_report_a_missing_dependency(app, name, vendor, attr, monkeypatch):
    """两个 SDK 现在随 base.txt 安装，这里模拟第三方环境缺包时的降级提示。"""
    module = module_of(app, name)
    monkeypatch.setattr(module, attr, None, raising=False)

    result = module.upimg_save("a.png", b"x", backend={"config": {}})
    assert result["code"] == 1
    assert result["message"] == "Please install %s module" % vendor


def test_disabled_processor_is_never_called(app):
    results = app.extensions["hooks"].call(
        "upimg_stream_processor", stream=b"x", suffix=".png"
    )
    assert results == []


def test_process_stream_rewrites_name_and_mime(monkeypatch):
    stub = StubManager(
        [{"code": 0, "data": {"stream": b"webp"}, "suffix": ".webp"}]
    )
    monkeypatch.setattr(images, "get_hook_manager", lambda: stub)

    stream, filename, mime = images.process_stream(b"jpeg", "photo.png", "image/png")

    assert stream == b"webp"
    assert filename == "photo.webp"
    assert mime == "image/webp"


def test_process_stream_ignores_failed_hooks(monkeypatch):
    #: 用老字段 msg：第三方处理器可能还没改，核心只判 code，不该受影响。
    stub = StubManager([{"code": 1, "msg": "boom"}])
    monkeypatch.setattr(images, "get_hook_manager", lambda: stub)

    assert images.process_stream(b"jpeg", "photo.png", "image/png") == (
        b"jpeg",
        "photo.png",
        "image/png",
    )


def test_process_stream_skips_videos(monkeypatch):
    monkeypatch.setattr(images, "get_hook_manager", lambda: StubManager([]))

    assert images.process_stream(b"video", "clip.mp4", "video/mp4") == (
        b"video",
        "clip.mp4",
        "video/mp4",
    )


def test_pic2webp_converts_a_png(app):
    module = module_of(app, "pic2webp")
    if module.Image is None:
        pytest.skip("Pillow is not installed")

    source = BytesIO()
    module.Image.new("RGB", (2, 2), "red").save(source, "PNG")
    result = module.upimg_stream_processor(source.getvalue(), ".png")

    assert result["code"] == 0
    assert result["suffix"] == ".webp"
    assert result["data"]["stream"][:4] == b"RIFF"


def test_pic2webp_keeps_transparency(app):
    module = module_of(app, "pic2webp")
    if module.Image is None:
        pytest.skip("Pillow is not installed")

    source = BytesIO()
    module.Image.new("RGBA", (2, 2), (255, 0, 0, 0)).save(source, "PNG")
    result = module.upimg_stream_processor(source.getvalue(), ".png")

    assert result["code"] == 0
    with module.Image.open(BytesIO(result["data"]["stream"])) as converted:
        assert converted.mode == "RGBA"
        assert converted.getpixel((0, 0))[3] == 0


def test_pic2webp_quality_is_configurable(app):
    module = module_of(app, "pic2webp")

    assert module._quality({"quality": 40}) == 40
    assert module._quality({"quality": 500}) == module.MAX_QUALITY
    assert module._quality({"quality": 0}) == module.DEFAULT_QUALITY
    assert module._quality({"quality": None}) == module.DEFAULT_QUALITY
    assert module._quality({}) == module.DEFAULT_QUALITY
