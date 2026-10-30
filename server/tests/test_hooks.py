# -*- coding: utf-8 -*-
from sapic.libs.hook import HookManager

GOOD_V1 = '''
__version__ = "1.0.0"
__author__ = "tester"

def upimg_save(**kwargs):
    return {"code": 0, "src": "v1"}
'''

GOOD_V2 = '''
__version__ = "2.0.0"
__author__ = "tester"

def upimg_save(**kwargs):
    return {"code": 0, "src": "v2"}
'''

BROKEN = '''
__version__ = "1.0.0"
__author__ = "tester"

def upimg_save(:
'''

STRICT = '''
__version__ = "1.0.0"
__author__ = "tester"

def upimg_save(filename, stream, upload_path=""):
    return {"code": 0, "filename": filename}
'''


def test_broken_hook_does_not_abort_scan(tmp_path):
    (tmp_path / "good.py").write_text(GOOD_V1, encoding="utf-8")
    (tmp_path / "bad.py").write_text(BROKEN, encoding="utf-8")

    manager = HookManager([tmp_path])
    assert set(manager.hooks) == {"good"}

    results = manager.call("upimg_save")
    assert len(results) == 1
    assert results[0]["code"] == 0
    assert results[0]["sender"] == "good"


def test_reload_picks_up_new_version(tmp_path):
    file = tmp_path / "good.py"
    file.write_text(GOOD_V1, encoding="utf-8")
    manager = HookManager([tmp_path])
    assert manager.get("good").meta["__version__"] == "1.0.0"

    file.write_text(GOOD_V2, encoding="utf-8")
    manager.reload()
    assert manager.get("good").meta["__version__"] == "2.0.0"


def test_hook_without_metadata_is_skipped(tmp_path):
    (tmp_path / "nometa.py").write_text(
        "def upimg_save(**kwargs):\n    return {'code': 0}\n",
        encoding="utf-8",
    )
    manager = HookManager([tmp_path])
    assert manager.hooks == {}


def test_kwargs_are_filtered_for_strict_signatures(tmp_path):
    (tmp_path / "strict.py").write_text(STRICT, encoding="utf-8")
    manager = HookManager([tmp_path])

    results = manager.call(
        "upimg_save",
        filename="a.png",
        stream=b"x",
        upload_path="",
        backend={"id": 1},
    )
    assert results[0]["code"] == 0
    assert results[0]["filename"] == "a.png"
