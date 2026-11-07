# -*- coding: utf-8 -*-
"""Third-party hook packages: validation, pip wiring, market and removal."""

import subprocess
import sys
from pathlib import Path

import pytest

from sapic.basis.errors import ApiError
from sapic.libs import hook_pkg
from sapic.models import User

USER = {
    "username": "bobby",
    "password": "secret123",
    "email": "bobby@example.com",
}


@pytest.fixture(autouse=True)
def _clear_market_cache():
    hook_pkg.clear_cache()
    yield
    hook_pkg.clear_cache()


def signin_admin(client, app):
    client.post("/api/v2/auth/register", json=USER)
    response = client.post(
        "/api/v2/auth/login",
        json={"username": USER["username"], "password": USER["password"]},
    )
    assert response.status_code == 200, response.get_json()
    with app.app_context():
        User.update(is_admin=True).where(User.username == USER["username"]).execute()
    return response.get_json()["data"]["csrf"]


@pytest.mark.parametrize(
    "name",
    ["sapic-hook-cos", "sapic_hook_cos", "pkg==1.2.3", "pkg[extra]", "pkg>=1.0"],
)
def test_valid_package_accepts_plain_specs(name):
    assert hook_pkg.valid_package(name)


@pytest.mark.parametrize(
    "name",
    ["", "-r", "--index-url", "../pkg", "pkg; rm -rf /", "pkg name", "pkg\n"],
)
def test_valid_package_rejects_injection(name):
    assert not hook_pkg.valid_package(name)


def test_pip_command_targets_configured_directory(app):
    with app.app_context():
        target = hook_pkg.require_package_dir()
        cmd = hook_pkg._pip_command("pkg==1.0", target, upgrade=True)

    assert cmd[:3] == [sys.executable, "-m", "pip"]
    assert cmd[cmd.index("--target") + 1] == str(target)
    assert "--upgrade" in cmd
    assert cmd[-1] == "pkg==1.0"
    #: 列表参数（不经 shell）是拒绝注入的关键。
    assert "-r" not in cmd


def test_install_rejects_bad_index_url(app):
    with app.app_context(), pytest.raises(ApiError):
        hook_pkg.install("pkg", index_url="file:///etc/passwd")


def test_install_reports_pip_failure(app, monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, "ERROR: no such package", "")

    monkeypatch.setattr(hook_pkg.subprocess, "run", fake_run)
    with app.app_context():
        result = hook_pkg.install("missing-pkg")

    assert result["ok"] is False
    assert result["code"] == 1
    assert "no such package" in result["output"]


def test_installed_versions_reads_dist_info(app):
    with app.app_context():
        target = hook_pkg.require_package_dir()
        (target / "sapic_hook_cos-1.2.3.dist-info").mkdir()
        assert hook_pkg.installed_versions() == {"sapic-hook-cos": "1.2.3"}


def test_remove_package_stays_inside_target(app):
    with app.app_context():
        target = hook_pkg.require_package_dir()
        package = target / "hookdemo"
        package.mkdir()
        (package / "__init__.py").write_text("__version__ = '1.0'\n", encoding="utf-8")
        single = target / "hookfile.py"
        single.write_text("__version__ = '1.0'\n", encoding="utf-8")
        outside = Path(target).parent / "keep.txt"
        outside.write_text("x", encoding="utf-8")

        removed = hook_pkg.remove_package("hookdemo")
        assert removed and not package.exists()
        #: 同目录下的其他包不受影响。
        assert single.exists()

        hook_pkg.remove_package("hookfile")
        assert not single.exists()
        #: 目录外文件不能被名字里的穿越路径带到。
        assert outside.exists()
        with pytest.raises(ApiError):
            hook_pkg.remove_package("../keep")


def test_market_items_normalize_and_cache(app, monkeypatch):
    calls = []

    def fake_fetch(url):
        calls.append(url)
        return [
            {
                "name": "cos",
                "module": "sapic_hook_cos",
                "desc": "腾讯云 COS",
                "github": "someone/sapic-hook-cos",
                "pypi": "sapic-hook-$name",
                "status": "stable",
            },
            {"name": "broken"},
        ]

    monkeypatch.setattr(hook_pkg, "_fetch_market", fake_fetch)
    with app.app_context():
        data = hook_pkg.market_items()
        again = hook_pkg.market_items()

    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["module"] == "sapic_hook_cos"
    assert item["github"] == "https://github.com/someone/sapic-hook-cos"
    assert item["package"] == "sapic-hook-cos"
    assert item["pypi"].startswith("https://pypi.org/project/")
    #: 六小时缓存：第二次不再请求远端。
    assert len(calls) == 1
    assert again["updated_at"] == data["updated_at"]

    with app.app_context():
        hook_pkg.market_items(refresh=True)
    assert len(calls) == 2


def test_packages_endpoint_reports_storage_dir(app, client):
    signin_admin(client, app)
    body = client.get("/api/v2/hooks/packages").get_json()
    assert body["code"] == "OK"
    assert body["data"]["configured"] is True
    assert Path(body["data"]["storage_dir"]).name == "hooks"


def test_market_endpoint_merges_loaded_state(app, client, monkeypatch):
    signin_admin(client, app)
    monkeypatch.setattr(
        hook_pkg,
        "_fetch_market",
        lambda url: [
            {
                "name": "up2local",
                "module": "up2local",
                "desc": "local driver",
                "github": "staugur/sapic",
            }
        ],
    )
    body = client.get("/api/v2/hooks/market").get_json()
    item = body["data"]["items"][0]
    #: 已加载的钩子即便没有 dist-info 也算已安装。
    assert item["loaded"] is True
    assert item["installed"] is True
    assert item["enabled"] is True


def _fake_market(url):
    return [
        {"name": "ext-%02d" % index, "module": "ext_%02d" % index}
        for index in range(23)
    ]


def test_market_endpoint_paginates(app, client, monkeypatch):
    signin_admin(client, app)
    monkeypatch.setattr(hook_pkg, "_fetch_market", _fake_market)

    first = client.get("/api/v2/hooks/market?page=1&page_size=10").get_json()["data"]
    assert [item["module"] for item in first["items"]] == [
        "ext_%02d" % index for index in range(10)
    ]
    assert (first["total"], first["page"], first["page_size"], first["pages"]) == (
        23,
        1,
        10,
        3,
    )

    last = client.get("/api/v2/hooks/market?page=3&page_size=10").get_json()["data"]
    assert len(last["items"]) == 3

    #: 超出范围的页码收敛到最后一页，而不是返回空表让用户以为没有数据。
    beyond = client.get("/api/v2/hooks/market?page=9&page_size=10").get_json()["data"]
    assert beyond["page"] == 3
    assert len(beyond["items"]) == 3
    assert beyond["total"] == 23

    #: 未指定时用默认页大小，超过上限的按上限算。
    default = client.get("/api/v2/hooks/market").get_json()["data"]
    assert default["page_size"] == hook_pkg.MARKET_PAGE_SIZE
    huge = client.get("/api/v2/hooks/market?page_size=1000").get_json()["data"]
    assert huge["page_size"] == hook_pkg.MAX_MARKET_PAGE_SIZE
    assert len(huge["items"]) == 23


def test_market_endpoint_rejects_invalid_page_params(app, client):
    signin_admin(client, app)
    for query in ("page=abc", "page_size=ten"):
        response = client.get("/api/v2/hooks/market?%s" % query)
        assert response.status_code == 400
        assert response.get_json()["code"] == "PARAM_ERROR"


def test_import_loads_hook_from_package_dir(app, client):
    """``HOOK_PKG_STORAGE_DIR`` 必须在 sys.path 上，模块名才能被引入。"""
    csrf = signin_admin(client, app)
    target = Path(app.config["HOOK_PKG_STORAGE_DIR"])
    module_file = target / "demohook.py"
    module_file.write_text(
        "__version__ = '1.0.0'\n__author__ = 'tester'\n__catalog__ = 'upload'\n",
        encoding="utf-8",
    )
    try:
        body = client.post(
            "/api/v2/hooks/import",
            json={"module": "demohook"},
            headers={"X-CSRF-Token": csrf},
        ).get_json()
        assert body["code"] == "OK", body
        assert body["data"]["item"]["name"] == "demohook"
        assert body["data"]["item"]["family"] == "third"
    finally:
        sys.modules.pop("demohook", None)
        if str(target) in sys.path:
            sys.path.remove(str(target))


def test_install_endpoint_returns_pip_result(app, client, monkeypatch):
    csrf = signin_admin(client, app)
    monkeypatch.setattr(
        hook_pkg,
        "install",
        lambda package, index_url="", upgrade=False: {
            "package": package,
            "ok": False,
            "code": 2,
            "output": "boom",
            "versions": {},
        },
    )
    body = client.post(
        "/api/v2/hooks/install",
        json={"package": "pkg"},
        headers={"X-CSRF-Token": csrf},
    ).get_json()
    assert body["code"] == "OK"
    assert body["data"]["install"]["ok"] is False
    assert body["data"]["install"]["output"] == "boom"
