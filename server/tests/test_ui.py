# -*- coding: utf-8 -*-
"""Declarative UI vocabulary: sanitising, pruning and result contracts."""

from sapic.libs import ui


def test_unknown_type_is_dropped():
    nodes = ui.clean_tree(
        [{"type": "iframe", "src": "x"}, {"type": "text", "text": "hi"}]
    )
    assert [node["type"] for node in nodes] == ["text"]


def test_unknown_keys_are_dropped():
    node = ui.clean_node(
        {"type": "text", "text": "hi", "onclick": "alert(1)", "class": "x"}
    )
    assert node == {"type": "text", "text": "hi"}


def test_unsafe_href_is_dropped():
    unsafe = {"type": "link", "text": "x", "href": "javascript:alert(1)"}
    assert ui.clean_node(unsafe) is None
    assert ui.clean_node({"type": "link", "text": "x", "href": "//evil.com"}) is None
    node = ui.clean_node(
        {"type": "link", "text": "x", "href": "/raw/{sha}"}, context={"sha": "abc"}
    )
    assert node["href"] == "/raw/abc"
    assert node["target"] == "self"


def test_button_must_use_a_declared_action():
    assert (
        ui.clean_node({"type": "button", "text": "x", "action": "rm"}, actions={"ping"})
        is None
    )
    node = ui.clean_node(
        {"type": "button", "text": "x", "action": "ping"}, actions={"ping"}
    )
    assert node["action"] == "ping"


def test_button_without_action_or_refresh_is_dropped():
    assert ui.clean_node({"type": "button", "text": "x"}) is None
    assert ui.clean_node({"type": "button", "text": "x", "refresh": True}) == {
        "type": "button",
        "text": "x",
        "refresh": True,
    }


def test_when_is_data_not_code():
    node = {
        "type": "text",
        "text": "hi",
        "when": {"field": "mode", "op": "eq", "value": "custom"},
    }
    assert ui.clean_node(node, values={"mode": "custom"})["text"] == "hi"
    assert ui.clean_node(node, values={"mode": "default"}) is None


def test_icon_must_come_from_the_builtin_sets():
    node = ui.clean_node(
        {"type": "link", "text": "x", "href": "/a", "icon": "fas fa-rocket"}
    )
    assert "icon" not in node
    node = ui.clean_node(
        {"type": "link", "text": "x", "href": "/a", "icon": "brand:github"}
    )
    assert node["icon"] == "brand:github"


def test_depth_is_capped():
    root = {"type": "row", "children": []}
    cursor = root
    for _ in range(ui.MAX_DEPTH + 3):
        child = {"type": "row", "children": []}
        cursor["children"].append(child)
        cursor = child

    node = ui.clean_node(root)
    depth = 0
    while node.get("children"):
        node = node["children"][0]
        depth += 1
    assert depth <= ui.MAX_DEPTH


def test_field_schema_is_cleaned():
    fields = ui.clean_fields(
        [
            {"key": "root", "type": "input", "label": "目录"},
            {"key": "root", "type": "input", "label": "重复"},
            {"key": "bad", "type": "iframe"},
            {"type": "input"},
        ]
    )
    assert [field["key"] for field in fields] == ["root"]


def test_number_field_keeps_bounds_and_numeric_default():
    fields = ui.clean_fields(
        [
            {
                "key": "quality",
                "type": "number",
                "label": "质量",
                "default": 75,
                "min": 1,
                "max": 100,
                "step": 5,
            }
        ]
    )
    assert fields == [
        {
            "type": "number",
            "key": "quality",
            "label": "质量",
            "default": 75,
            "min": 1,
            "max": 100,
            "step": 5,
        }
    ]


def test_slot_mode_is_restricted():
    assert ui.clean_slots(
        [{"name": "profile"}, {"name": "profile", "mode": "esm"}, {"name": "nope"}]
    ) == [{"name": "profile", "mode": "declarative"}]


def test_action_result_is_normalised():
    assert ui.clean_result({"code": 1, "msg": "boom"}) == {
        "code": 1,
        "message": "boom",
    }
    assert ui.clean_result(
        {"code": 0, "toast": {"level": "success", "text": "ok"}, "refresh": True}
    ) == {"code": 0, "toast": {"level": "success", "text": "ok"}, "refresh": True}
    assert ui.clean_result({"code": 0, "toast": {"level": "evil", "text": "x"}}) == {
        "code": 0
    }


def test_dataset_is_normalised():
    assert ui.clean_dataset({"items": [{"a": 1, "b": {"c": 2}}], "total": 3}) == {
        "items": [{"a": 1}],
        "total": 3,
    }
    assert ui.clean_dataset(None) == {"items": [], "total": 0}
