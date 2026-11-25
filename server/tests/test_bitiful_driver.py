# -*- coding: utf-8 -*-
"""``up2bitiful``: the Bitiful S4 driver, which speaks S3 through boto3."""

from io import BytesIO

from sapic.libs import ext
from sapic.libs.hook import get_hook_manager


class FakeClientError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.response = {"Error": {"Code": code, "Message": message}}


class FakeS4:
    def __init__(self):
        self.saved = []
        self.deleted = []
        self.presigned = []
        self.errors = {}

    def put_object(self, **kwargs):
        if "put" in self.errors:
            raise self.errors["put"]
        self.saved.append(kwargs)
        return {"ETag": '"etag-value"'}

    def delete_object(self, **kwargs):
        self.deleted.append(kwargs)
        return {}

    def head_object(self, **kwargs):
        raise FakeClientError("404", "Not Found")

    def generate_presigned_url(self, operation, Params=None, ExpiresIn=0):
        self.presigned.append((operation, Params, ExpiresIn))
        return "https://s3.bitiful.net/%s/%s?X-Amz-Expires=%d" % (
            Params["Bucket"],
            Params["Key"],
            ExpiresIn,
        )


def module_of(app):
    with app.app_context():
        return get_hook_manager().get("up2bitiful").module


def use_fake(monkeypatch, module, client):
    monkeypatch.setattr(module, "_client", lambda config: (client, ""))


def test_bitiful_driver_declares_the_upload_contract(app):
    with app.app_context():
        hook = get_hook_manager().get("up2bitiful")
        assert hook.meta["__catalog__"] == "upload"
        assert hook.meta["__state__"] == "disabled"
        assert ext.supports_private_read(hook.module) is True
        manifest = get_hook_manager().manifest("up2bitiful")

    keys = [field["key"] for field in manifest["config_schema"]]
    assert keys == [
        "domain",
        "thumb_suffix",
        "bucket",
        "access_key",
        "secret_key",
        "basedir",
    ]
    assert [action["name"] for action in manifest["actions"]] == ["ping"]


def test_bitiful_save_returns_the_object_key(app, monkeypatch):
    module = module_of(app)
    fake = FakeS4()
    use_fake(monkeypatch, module, fake)

    result = module.upimg_save(
        "photo.png",
        BytesIO(b"bytes"),
        "alice/2026",
        backend={
            "config": {
                "bucket": "demo",
                "basedir": "/img/",
                "domain": "https://img.example.com/",
            }
        },
    )

    assert result == {
        "code": 0,
        "path": "img/alice/2026/photo.png",
        "size": 5,
        "etag": "etag-value",
        "src": "https://img.example.com/img/alice/2026/photo.png",
    }
    assert fake.saved[0]["Bucket"] == "demo"
    assert fake.saved[0]["Key"] == "img/alice/2026/photo.png"
    assert fake.saved[0]["ContentType"] == "image/png"


def test_bitiful_save_omits_src_without_a_domain(app, monkeypatch):
    module = module_of(app)
    use_fake(monkeypatch, module, FakeS4())

    result = module.upimg_save(
        "a.png", b"x", backend={"config": {"bucket": "demo"}}
    )

    assert result["code"] == 0
    assert "src" not in result


def test_bitiful_read_url_is_presigned_and_clamped(app, monkeypatch):
    module = module_of(app)
    fake = FakeS4()
    use_fake(monkeypatch, module, fake)

    result = module.upimg_url(
        {"path": "pics/a.png"},
        backend={"config": {"bucket": "demo"}},
        expires=module.MAX_EXPIRES * 2,
    )

    assert result["code"] == 0
    assert result["url"] == (
        "https://s3.bitiful.net/demo/pics/a.png?X-Amz-Expires=%d"
        % module.MAX_EXPIRES
    )
    assert fake.presigned == [
        ("get_object", {"Bucket": "demo", "Key": "pics/a.png"}, module.MAX_EXPIRES)
    ]


def test_bitiful_delete_uses_the_stored_key(app, monkeypatch):
    module = module_of(app)
    fake = FakeS4()
    use_fake(monkeypatch, module, fake)

    result = module.upimg_delete(
        "sha",
        "alice/2026",
        "photo.png",
        "",
        {"path": "img/alice/2026/photo.png"},
        backend={"config": {"bucket": "demo"}},
    )

    assert result["code"] == 0
    assert fake.deleted == [{"Bucket": "demo", "Key": "img/alice/2026/photo.png"}]


def test_bitiful_reports_the_s3_error_code(app, monkeypatch):
    module = module_of(app)
    fake = FakeS4()
    fake.errors["put"] = FakeClientError("AccessDenied", "denied")
    use_fake(monkeypatch, module, fake)

    result = module.upimg_save(
        "a.png", b"x", backend={"config": {"bucket": "demo"}}
    )

    assert result["code"] == 1
    assert result["message"] == "AccessDenied: denied"


def test_bitiful_ping_accepts_a_missing_probe_object(app, monkeypatch):
    module = module_of(app)
    use_fake(monkeypatch, module, FakeS4())

    result = module.action_ping(
        values={},
        context={
            "backend": {
                "config": {
                    "bucket": "demo",
                    "access_key": "ak",
                    "secret_key": "sk",
                }
            }
        },
    )

    assert result["code"] == 0
    assert result["toast"]["level"] == "success"


def test_bitiful_reports_a_missing_dependency(app, monkeypatch):
    module = module_of(app)
    monkeypatch.setattr(module, "boto3", None)

    result = module.upimg_save("a.png", b"x", backend={"config": {}})
    assert result == {"code": 1, "message": "Please install boto3 module"}
