# -*- coding: utf-8 -*-
"""Sphinx configuration for the sapic documentation.

The version is read from ``server/sapic/version.py`` instead of importing the
package: the documentation build must not need Flask, Peewee or a database.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO / "server"))


def _read_version() -> str:
    """Current ``__version__`` of the sapic package."""
    source = (REPO / "server" / "sapic" / "version.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', source)
    return match.group(1) if match else "0.0.0"


project = "sapic"
author = "staugur"
copyright = "2026, staugur"
release = _read_version()
version = release
language = "zh_CN"

extensions = [
    "myst_parser",
    "sphinx.ext.extlinks",
]

source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
root_doc = "index"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
]
myst_heading_anchors = 3

extlinks = {
    "repo": ("https://github.com/sapicd/sapic/tree/master/%s", "%s"),
    "pypi": ("https://pypi.org/project/%s", "%s"),
}

html_theme = "furo"
html_title = "sapic 文档"
htmlhelp_basename = "sapicdoc"
html_static_path: list[str] = []

#: 侧栏 / 移动端头部与浏览器标签页复用前端的品牌资源，避免另存一份。
html_logo = "../web/public/logo.png"
html_favicon = "../web/public/favicon.png"
html_theme_options = {
    "source_repository": "https://github.com/sapicd/sapic/",
    "source_branch": "master",
    "source_directory": "docs/",
}

#: The docs are built with ``-W`` on CI / Read the Docs: keep the build clean.
nitpicky = False
