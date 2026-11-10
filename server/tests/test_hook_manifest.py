# -*- coding: utf-8 -*-
"""HookManager manifest aggregation, slots, actions and datasets."""

from sapic.libs.hook import HookManager

DEMO = '''
__version__ = "1.0.0"
__author__ = "tester"


def hook_manifest():
    return {
        "title": "Demo",
        "catalog": "upload",
        "config_schema": [{"key": "root", "type": "input", "label": "Root"}],
        "actions": [{"name": "ping", "label": "Ping"}],
        "data_sources": [{"name": "items", "label": "Items"}],
        "slots": [{"name": "nav"}],
    }


def slot_nav(**kwargs):
    return [{"type": "button", "text": "Ping", "action": "ping"}]


def action_ping(**kwargs):
    return {"code": 0, "toast": {"level": "success", "text": "pong"}}


def data_items(**kwargs):
    return {"items": [{"name": "a"}], "total": 1}
'''

LEGACY = '''
__version__ = "1.0.0"
__author__ = "tester"
__description__ = "legacy driver"
__catalog__ = "upload"
'''

BROKEN_SLOT = '''
__version__ = "1.0.0"
__author__ = "tester"


def hook_manifest():
    return {"title": "Broken", "slots": [{"name": "nav"}]}


def slot_nav(**kwargs):
    raise RuntimeError("boom")
'''


def test_legacy_hook_gets_a_default_manifest(tmp_path):
    (tmp_path / "legacy.py").write_text(LEGACY, encoding="utf-8")
    manager = HookManager([tmp_path])

    manifest = manager.manifest("legacy")
    assert manifest["title"] == "legacy"
    assert manifest["description"] == "legacy driver"
    assert manifest["catalog"] == "upload"
    assert manifest["slots"] == []
    assert manifest["actions"] == []


def test_manifest_is_validated(tmp_path):
    (tmp_path / "demo.py").write_text(DEMO, encoding="utf-8")
    manager = HookManager([tmp_path])

    manifest = manager.manifest("demo")
    assert manifest["ui_version"] == 1
    assert [field["key"] for field in manifest["config_schema"]] == ["root"]
    assert manifest["slots"] == [{"name": "nav", "mode": "declarative"}]


def test_manifests_can_be_limited_to_slots(tmp_path):
    (tmp_path / "demo.py").write_text(DEMO, encoding="utf-8")
    manager = HookManager([tmp_path])

    assert manager.manifests(slots=("profile",))[0]["slots"] == []
    assert manager.manifests(slots=("nav",))[0]["slots"] == [
        {"name": "nav", "mode": "declarative"}
    ]


def test_slot_renders_declared_nodes(tmp_path):
    (tmp_path / "demo.py").write_text(DEMO, encoding="utf-8")
    manager = HookManager([tmp_path])

    blocks = manager.slot("nav")
    assert blocks[0]["hook"] == "demo"
    assert blocks[0]["nodes"] == [
        {"type": "button", "text": "Ping", "action": "ping"}
    ]


def test_slot_skips_hooks_that_do_not_declare_it(tmp_path):
    (tmp_path / "demo.py").write_text(DEMO, encoding="utf-8")
    manager = HookManager([tmp_path])

    assert manager.slot("profile") == []
    assert manager.slot("unknown.slot") == []


def test_broken_slot_does_not_abort_others(tmp_path):
    (tmp_path / "broken.py").write_text(BROKEN_SLOT, encoding="utf-8")
    (tmp_path / "demo.py").write_text(DEMO, encoding="utf-8")
    manager = HookManager([tmp_path])

    hooks = [block["hook"] for block in manager.slot("nav")]
    assert hooks == ["demo"]


def test_action_dispatch(tmp_path):
    (tmp_path / "demo.py").write_text(DEMO, encoding="utf-8")
    manager = HookManager([tmp_path])

    assert manager.action("demo", "ping") == {
        "code": 0,
        "toast": {"level": "success", "text": "pong"},
    }
    assert manager.action("demo", "undeclared") is None
    assert manager.action("missing", "ping") is None


def test_dataset_dispatch(tmp_path):
    (tmp_path / "demo.py").write_text(DEMO, encoding="utf-8")
    manager = HookManager([tmp_path])

    assert manager.data("demo", "items") == {"items": [{"name": "a"}], "total": 1}
    assert manager.data("demo", "missing") == {"items": [], "total": 0}


def test_reload_refreshes_the_manifest(tmp_path):
    file = tmp_path / "demo.py"
    file.write_text(DEMO, encoding="utf-8")
    manager = HookManager([tmp_path])
    assert manager.manifest("demo")["title"] == "Demo"

    file.write_text(DEMO.replace('"Demo"', '"Demo2"'), encoding="utf-8")
    manager.reload()
    assert manager.manifest("demo")["title"] == "Demo2"
