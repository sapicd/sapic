# -*- coding: utf-8 -*-
"""Hook manager.

Keeps the v1 plugin contract (metadata fields, ``upimg_save`` /
``upimg_delete``) while fixing the reliability issues of the old loader:

- one broken hook can no longer abort the whole scan;
- reloads build a new snapshot and swap it atomically;
- a failed reload keeps serving the previous snapshot;
- hook modules are re-executed from their current source (no stale
  ``sys.modules`` entries).
"""

from __future__ import annotations

import inspect
import logging
import sys
import time
from dataclasses import dataclass
from hashlib import md5
from pathlib import Path
from threading import RLock
from types import ModuleType

from flask import current_app

logger = logging.getLogger(__name__)

META_FIELDS = (
    "__version__",
    "__author__",
    "__description__",
    "__catalog__",
    "__hookname__",
    "__state__",
    "__appversion__",
)


@dataclass(frozen=True)
class Hook:
    name: str
    module: ModuleType
    path: str
    meta: dict
    enabled: bool


class HookManager:
    """Load hooks from one or more directories with hot reload support."""

    def __init__(self, paths, reload_interval: int = 600):
        self.paths = [Path(p) for p in paths if p]
        self.reload_interval = max(int(reload_interval or 0), 0)
        self._hooks: dict[str, Hook] = {}
        self._signature = ""
        self._last_scan = 0.0
        self._lock = RLock()

    # -- discovery -----------------------------------------------------
    def _iter_sources(self):
        seen = set()
        for root in self.paths:
            if not root.is_dir():
                continue
            for file in sorted(root.glob("*.py")):
                if file.name.startswith("_"):
                    continue
                if file.stem in seen:
                    continue
                seen.add(file.stem)
                yield file.stem, file
            for child in sorted(root.iterdir()):
                init = child / "__init__.py"
                if child.is_dir() and init.is_file() and child.name not in seen:
                    seen.add(child.name)
                    yield child.name, init

    def _compute_signature(self) -> str:
        digest = md5()
        for name, file in self._iter_sources():
            try:
                stat = file.stat()
            except OSError:
                continue
            digest.update(
                ("%s:%s:%s" % (name, stat.st_mtime_ns, stat.st_size)).encode()
            )
        return digest.hexdigest()

    def _load(self, name: str, file: Path) -> Hook | None:
        module_name = "sapic_hooks.%s" % name
        #: Compile the source directly instead of using the import machinery:
        #: bytecode caches key on (mtime seconds, size), so a hook edited in
        #: place within the same second could keep running the old code.
        source = file.read_text(encoding="utf-8")
        code = compile(source, str(file), "exec")

        module = ModuleType(module_name)
        module.__file__ = str(file)
        module.__package__ = module_name.rpartition(".")[0]
        if file.name == "__init__.py":
            module.__path__ = [str(file.parent)]

        #: Required for relative imports inside third-party hook packages.
        sys.modules[module_name] = module
        try:
            exec(code, module.__dict__)
        except Exception:
            sys.modules.pop(module_name, None)
            raise

        if not getattr(module, "__version__", None) or not getattr(
            module, "__author__", None
        ):
            logger.warning("Hook %s skipped: missing __version__/__author__", name)
            sys.modules.pop(module_name, None)
            return None

        meta = {field: getattr(module, field, None) for field in META_FIELDS}
        enabled = (meta.get("__state__") or "enabled") != "disabled"
        return Hook(
            name=name,
            module=module,
            path=str(file),
            meta=meta,
            enabled=enabled,
        )

    def reload(self) -> None:
        """Rebuild the hook snapshot; keep the old one if every load fails."""
        hooks: dict[str, Hook] = {}
        for name, file in self._iter_sources():
            try:
                hook = self._load(name, file)
            except Exception:
                logger.exception("Failed to load hook %s", name)
                continue
            if hook is not None:
                hooks[name] = hook

        with self._lock:
            if hooks or not self._hooks:
                self._hooks = hooks
            self._signature = self._compute_signature()
            self._last_scan = time.time()

    def ensure_fresh(self, force: bool = False) -> None:
        now = time.time()
        if not force and now - self._last_scan < 1:
            return
        if force or not self._hooks:
            self.reload()
            return
        if now - self._last_scan >= self.reload_interval:
            if self._compute_signature() != self._signature:
                self.reload()
            else:
                self._last_scan = now

    # -- public API ----------------------------------------------------
    @property
    def hooks(self) -> dict[str, Hook]:
        self.ensure_fresh()
        with self._lock:
            return dict(self._hooks)

    def get(self, name: str) -> Hook | None:
        return self.hooks.get(name)

    def info(self) -> list[dict]:
        return [
            {
                "name": hook.name,
                "path": hook.path,
                "enabled": hook.enabled,
                **{k: v for k, v in hook.meta.items() if v is not None},
            }
            for hook in self.hooks.values()
        ]

    @staticmethod
    def _accepted_kwargs(func, kwargs: dict) -> dict:
        """Filter kwargs for drivers written against the v1 signature."""
        try:
            parameters = inspect.signature(func).parameters
        except (TypeError, ValueError):
            return kwargs
        if any(
            param.kind is inspect.Parameter.VAR_KEYWORD
            for param in parameters.values()
        ):
            return kwargs
        return {key: value for key, value in kwargs.items() if key in parameters}

    def call(self, funcname: str, include=None, **kwargs) -> list[dict]:
        """Call ``funcname`` on matching hooks and collect their results.

        Mirrors v1 semantics: a failing hook produces ``code=1`` instead of
        aborting the whole call, and ``sender`` records the hook name.
        """
        includes = set(include) if include else None
        results = []
        for name in sorted(self.hooks):
            hook = self.hooks[name]
            if includes is not None and name not in includes:
                continue
            if not hook.enabled:
                continue
            func = getattr(hook.module, funcname, None)
            if not callable(func):
                continue
            try:
                result = func(**self._accepted_kwargs(func, kwargs))
            except Exception as exc:
                logger.exception("Hook %s.%s failed", name, funcname)
                result = {"code": 1, "msg": str(exc)}
            result = dict(result or {})
            result.setdefault("sender", name)
            results.append(result)
        return results


def init_app(app) -> None:
    from pathlib import Path as _Path

    paths = [_Path(__file__).resolve().parent.parent / "hooks"]
    extra = app.config.get("HOOK_PKG_STORAGE_DIR")
    if extra:
        paths.append(_Path(extra))
    app.extensions["hooks"] = HookManager(
        paths, app.config.get("HOOK_RELOAD_TIME", 600)
    )


def get_hook_manager() -> HookManager:
    return current_app.extensions["hooks"]
