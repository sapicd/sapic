# -*- coding: utf-8 -*-
"""sapic.libs.hook_pkg

Third-party hook packages: local inventory, ``pip install`` and the official
market listing.

Installing a package from the web console means running arbitrary code inside
the server process, so everything here is invoked from admin-only endpoints:

- the target directory always comes from the config, never from the request;
- package names and the index URL are validated before they reach ``pip``;
- ``pip`` runs as a list argument (no shell) with a hard timeout.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from threading import RLock
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import current_app

from ..basis.errors import ApiError, ErrorCode
from ..basis.vars import DEFAULT_HOOK_MARKET_URL

logger = logging.getLogger(__name__)

#: Charset accepted for ``name`` / ``name[extra]`` / ``name==1.2`` style specs.
PACKAGE_RE = re.compile(
    r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}"
    r"(\[[A-Za-z0-9,._-]{1,64}\])?"
    r"((==|>=|<=|~=|!=|>|<)[0-9A-Za-z.*+!_-]{1,32})?\Z"
)

#: Market listing cache lifetime, in seconds.
MARKET_TTL = 6 * 3600

#: Default page size of the market listing and the upper bound a caller may ask
#: for; the whole list is cached locally, only the window is returned.
MARKET_PAGE_SIZE = 10
MAX_MARKET_PAGE_SIZE = 100

#: Upper bound for one ``pip install`` run.
PIP_TIMEOUT = 180

#: Only the tail of the pip log is useful to the browser.
PIP_LOG_LIMIT = 4000

_cache_lock = RLock()
_cache_items: list[dict] | None = None
_cache_ts = 0.0


def valid_package(name: str) -> bool:
    """Whether ``name`` is a plain requirement spec safe to hand to pip."""
    return bool(PACKAGE_RE.match(str(name or "")))


def package_dir() -> Path | None:
    """Directory that receives third-party packages, ``None`` when disabled."""
    raw = str(current_app.config.get("HOOK_PKG_STORAGE_DIR") or "").strip()
    return Path(raw) if raw else None


def require_package_dir() -> Path:
    """The package directory, created on demand; 400 when it is not configured."""
    path = package_dir()
    if path is None:
        raise ApiError(
            "HOOK_PKG_STORAGE_DIR is not configured",
            ErrorCode.PARAM_ERROR,
        )
    path.mkdir(parents=True, exist_ok=True)
    return path


def installed_versions() -> dict[str, str]:
    """``{normalized package name: version}`` read from ``*.dist-info`` folders."""
    target = package_dir()
    if target is None or not target.is_dir():
        return {}
    versions: dict[str, str] = {}
    for entry in sorted(target.iterdir()):
        if not entry.is_dir() or not entry.name.endswith(".dist-info"):
            continue
        stem = entry.name[: -len(".dist-info")]
        name, _, version = stem.partition("-")
        if name:
            versions[name.lower().replace("_", "-")] = version
    return versions


def _pip_command(
    package: str, target: Path, index_url: str = "", upgrade: bool = False
) -> list[str]:
    """Build the pip argv; kept separate so tests can assert the shape."""
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--no-input",
        "--no-color",
        "--no-cache-dir",
        "--progress-bar",
        "off",
        "--disable-pip-version-check",
        "--timeout",
        "15",
        "--retries",
        "2",
        "--target",
        str(target),
    ]
    if upgrade:
        cmd.append("--upgrade")
    if index_url:
        cmd.extend(["--index-url", index_url])
    cmd.append(package)
    return cmd


def install(
    package: str, index_url: str = "", upgrade: bool = False
) -> dict:
    """Install one package into the hook package directory.

    Returns ``{"package", "ok", "code", "output", "versions"}``; a failing pip
    run is reported through ``ok=False`` so the caller can show the log instead
    of losing it in an error message.
    """
    name = str(package or "").strip()
    if not valid_package(name):
        raise ApiError("invalid package name", ErrorCode.PARAM_ERROR)

    index = str(index_url or "").strip()
    if index and not index.startswith(("http://", "https://")):
        raise ApiError("index_url must be an http(s) URL", ErrorCode.PARAM_ERROR)

    target = require_package_dir()
    cmd = _pip_command(name, target, index, upgrade)
    logger.info("Running pip install for %s into %s", name, target)
    try:
        done = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=PIP_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ApiError(
            "pip install timed out after %s seconds" % PIP_TIMEOUT,
            ErrorCode.SERVICE_UNAVAILABLE,
            503,
        ) from exc
    except OSError as exc:
        raise ApiError(
            "failed to run pip: %s" % exc,
            ErrorCode.INTERNAL_ERROR,
            500,
        ) from exc

    output = ((done.stdout or "") + (done.stderr or "")).strip()
    clear_cache()
    return {
        "package": name,
        "ok": done.returncode == 0,
        "code": done.returncode,
        "output": output[-PIP_LOG_LIMIT:],
        "versions": installed_versions(),
    }


def remove_package(module: str) -> list[str]:
    """Delete the files of a package installed into the hook directory.

    Only paths directly under the configured directory are touched, so a
    crafted module name (``../..``) cannot escape it. Missing files are fine.
    """
    target = require_package_dir()
    root = target.resolve()
    top = str(module or "").split(".")[0].strip()
    if not top or top.startswith(".") or "/" in top or "\\" in top:
        raise ApiError("invalid module name", ErrorCode.PARAM_ERROR)

    removed: list[str] = []
    for candidate in (root / ("%s.py" % top), root / top):
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if root not in resolved.parents:
            continue
        if resolved.is_dir():
            shutil.rmtree(resolved)
        elif resolved.is_file():
            resolved.unlink()
        else:
            continue
        removed.append(str(resolved))
    clear_cache()
    return removed


def market_url() -> str:
    """Configured market listing URL, falling back to the official one."""
    return str(current_app.config.get("HOOK_MARKET_URL") or "").strip() or (
        DEFAULT_HOOK_MARKET_URL
    )


def _fetch_market(url: str) -> list[dict]:
    """Download and parse the market listing (a JSON array)."""
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github.v3.raw",
            "User-Agent": "sapic-hook-market",
        },
    )
    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read(2 * 1024 * 1024)
    except (HTTPError, URLError, OSError) as exc:
        raise ApiError(
            "failed to fetch hook market: %s" % exc,
            ErrorCode.SERVICE_UNAVAILABLE,
            503,
        ) from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ApiError(
            "hook market returned invalid JSON",
            ErrorCode.SERVICE_UNAVAILABLE,
            503,
        ) from exc
    if not isinstance(data, list):
        raise ApiError(
            "hook market returned an unexpected payload",
            ErrorCode.SERVICE_UNAVAILABLE,
            503,
        )
    return data


def _normalize(item: dict, versions: dict[str, str]) -> dict | None:
    """One market entry in the shape the front-end renders."""
    name = str(item.get("name") or "").strip()
    module = str(item.get("module") or "").strip()
    if not name or not module:
        return None

    github = str(item.get("github") or "").strip()
    if github and not github.startswith("http"):
        github = "https://github.com/%s" % github
    package = str(item.get("pypi") or "").replace("$name", name).strip()
    return {
        "name": name,
        "module": module,
        "description": str(item.get("desc") or "").strip(),
        "author": str(item.get("author") or "").strip(),
        "home": str(item.get("home") or "").strip() or github,
        "github": github,
        "package": package,
        "pypi": "https://pypi.org/project/%s" % package if package else "",
        "status": str(item.get("status") or "").strip(),
        "installed_version": versions.get(
            package.lower().replace("_", "-"), ""
        )
        if package
        else "",
    }


def market_items(refresh: bool = False) -> dict:
    """Market entries plus the cache timestamp.

    The listing comes from a public GitHub file, so a six-hour cache keeps the
    unauthenticated API rate limit out of reach; ``refresh`` bypasses it.
    """
    global _cache_items, _cache_ts

    now = time.time()
    with _cache_lock:
        if (
            not refresh
            and _cache_items is not None
            and now - _cache_ts < MARKET_TTL
        ):
            return {"items": list(_cache_items), "updated_at": int(_cache_ts)}

    raw = _fetch_market(market_url())
    versions = installed_versions()
    items = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        entry = _normalize(item, versions)
        if entry is not None:
            items.append(entry)

    with _cache_lock:
        _cache_items = items
        _cache_ts = time.time()
        return {"items": list(items), "updated_at": int(_cache_ts)}


def clear_cache() -> None:
    """Drop the market cache after an install/removal changes versions."""
    global _cache_items, _cache_ts
    with _cache_lock:
        _cache_items = None
        _cache_ts = 0.0
