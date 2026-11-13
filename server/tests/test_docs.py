# -*- coding: utf-8 -*-
import json
import re

import pytest

from sapic.libs.openapi import (
    HIDDEN_BLUEPRINTS,
    HIDDEN_ENDPOINTS,
    OPERATIONS,
    _convert_path,
)
from sapic.version import __version__


@pytest.fixture()
def spec(client):
    response = client.get("/api/v2/openapi.json")
    assert response.status_code == 200
    return response.get_json()


def test_openapi_document_is_served(spec):
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["version"] == __version__
    #: 文档接口自己返回 JSON，导入客户端时保留它是完整的。
    assert "/api/v2/openapi.json" in spec["paths"]
    #: Swagger 页面是 HTML，不属于 JSON API。
    assert "/api/v2/docs" not in spec["paths"]
    #: Flask 的静态目录不是 API，不要混进文档。
    assert "/static/{filename}" not in spec["paths"]


def test_every_route_appears_in_the_document(app, spec):
    """路由表是唯一来源：新增蓝图漏写描述也要出现，不能静默缺失。"""
    documented = {
        (path, method)
        for path, operations in spec["paths"].items()
        for method in operations
    }
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static" or rule.rule.startswith("/static/"):
            continue
        if rule.endpoint in HIDDEN_ENDPOINTS:
            continue
        if rule.endpoint.split(".", 1)[0] in HIDDEN_BLUEPRINTS:
            continue
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            assert (_convert_path(rule.rule), method.lower()) in documented, (
                rule.rule,
                method,
            )


def test_noise_endpoints_are_hidden(spec):
    """根路径与油猴脚本没有可试的 JSON 契约，不进文档。"""
    assert "/" not in spec["paths"]
    assert "/api/v2/userscript.user.js" not in spec["paths"]


def test_operation_metadata_matches_real_endpoints(app):
    """元数据键写错时只是一条永不生效的配置，这里把它挡在测试里。"""
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    assert set(OPERATIONS) <= endpoints


def test_upload_allows_anonymous_credentials(spec):
    upload = spec["paths"]["/api/v2/upload"]["post"]
    kinds = upload["requestBody"]["content"]
    assert "multipart/form-data" in kinds
    fields = kinds["multipart/form-data"]["schema"]["properties"]
    assert {"file", "url", "album_id", "expire"} <= set(fields)
    #: 空对象表示「也可以不带凭据」，与匿名上传一致。
    assert upload["security"] == [{"session": []}, {"pat": []}, {}]
    assert upload["responses"]["201"]
    assert upload["responses"]["413"]


def test_image_endpoints_declare_parameters(spec):
    listing = spec["paths"]["/api/v2/images"]["get"]
    names = {param["name"] for param in listing["parameters"]}
    assert {"scope", "album_id", "keyword", "tag", "cursor", "page"} <= names
    assert listing["security"] == [{"session": []}, {"pat": []}]

    detail = spec["paths"]["/api/v2/images/{sha}"]["get"]
    path_param = [p for p in detail["parameters"] if p["in"] == "path"][0]
    assert path_param["name"] == "sha"
    assert path_param["required"] is True
    assert path_param["description"]


def test_album_ids_are_integers(spec):
    rule = spec["paths"]["/api/v2/albums/{album_id}/shares/{user_id}"]["patch"]
    types = {p["name"]: p["schema"]["type"] for p in rule["parameters"]}
    assert types == {"album_id": "integer", "user_id": "integer"}


def test_admin_and_hook_routes_are_hidden(spec):
    """管理接口与钩子插件接口这版不对外出文档，连路由也不列。"""
    assert "/api/v2/settings" not in spec["paths"]
    assert "/api/v2/settings/version" not in spec["paths"]
    assert "/api/v2/users" not in spec["paths"]
    assert "/api/v2/backends" not in spec["paths"]
    assert "/api/v2/me/backends" not in spec["paths"]
    assert not [p for p in spec["paths"] if p.startswith("/api/v2/hooks")]


def test_public_endpoints_require_no_credentials(spec):
    assert spec["paths"]["/api/v2/site"]["get"]["security"] == []
    assert spec["paths"]["/api/v2/health"]["get"]["security"] == []


def test_non_json_endpoints_are_hidden(spec):
    """文档只描述 JSON API：HTML 页面、302 跳转与图片字节流都不进文档。"""
    assert "/api/v2/docs" not in spec["paths"]
    assert "/raw/{sha}" not in spec["paths"]
    assert "/i/{sha}" not in spec["paths"]


def test_references_and_operation_ids_are_valid(spec):
    """`$ref` 写错时 Swagger UI 只会静默少显示，这里直接挡下来。"""
    schemas = set(spec["components"]["schemas"])
    refs = set(re.findall(r'"\$ref": "#/components/schemas/([^"]+)"', json.dumps(spec)))
    assert refs <= schemas

    operation_ids = [
        operation["operationId"]
        for operations in spec["paths"].values()
        for operation in operations.values()
    ]
    assert len(operation_ids) == len(set(operation_ids))
    assert all(
        operation.get("summary") and operation.get("responses")
        for operations in spec["paths"].values()
        for operation in operations.values()
    )


def test_docs_page_renders_swagger_ui(client):
    response = client.get("/api/v2/docs")
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    page = response.get_data(as_text=True)
    assert "SwaggerUIBundle" in page
    #: 页面必须指向本站的 JSON，而不是外部地址。
    assert "/api/v2/openapi.json" in page
