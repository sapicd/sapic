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

import importlib
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

from ..basis.vars import HOOK_RELOAD_TIME
from . import ui
from .settings import get_setting

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

#: Upper bound for imported (third-party) modules; keeps the scan predictable.
MAX_IMPORTED = 32


@dataclass(frozen=True)
class Hook:
    name: str
    module: ModuleType
    path: str
    meta: dict
    enabled: bool
    family: str = "local"


class HookManager:
    """Load hooks from one or more directories with hot reload support.

    ``state_provider`` is an optional callable returning ``{name: enabled}``; it
    lets the application persist the admin's enable/disable choice while the
    manager stays usable without an app context (tests pass ``None``).

    ``imported_provider`` returns a list of importable module names, which is
    how third-party hooks are installed: the module lives in site-packages and
    is imported instead of scanned from :attr:`paths`.
    """

    def __init__(
        self,
        paths,
        reload_interval: int = 600,
        state_provider=None,
        imported_provider=None,
    ):
        self.paths = [Path(p) for p in paths if p]
        self.reload_interval = max(int(reload_interval or 0), 0)
        self.state_provider = state_provider
        self.imported_provider = imported_provider
        self._states: dict[str, bool] = {}
        self._imported: list[str] = []
        self._hooks: dict[str, Hook] = {}
        self._manifests: dict[str, dict] = {}
        self._signature = ""
        self._last_scan = 0.0
        self._lock = RLock()

    def _read_states(self) -> dict[str, bool]:
        """Read the persisted states; ``__state__`` is the fallback."""
        if self.state_provider is None:
            return {}
        try:
            data = self.state_provider() or {}
        except Exception:
            logger.exception("Failed to read hook states, using __state__")
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(name): bool(value) for name, value in data.items()}

    def _read_imported(self) -> list[str]:
        """Read the module names registered by the admin."""
        if self.imported_provider is None:
            return []
        try:
            data = self.imported_provider() or []
        except Exception:
            logger.exception("Failed to read imported hooks")
            return []
        if isinstance(data, str):
            data = [data]
        if not isinstance(data, (list, tuple)):
            return []
        names = []
        for item in data:
            name = str(item or "").strip()
            if name and name not in names:
                names.append(name)
        return names[:MAX_IMPORTED]

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

        hook = self._build_hook(name, module, str(file), "local")
        if hook is None:
            sys.modules.pop(module_name, None)
        return hook

    def _build_hook(
        self, name: str, module: ModuleType, path: str, family: str = "local"
    ) -> Hook | None:
        """Validate the metadata of a loaded module and compute its state."""
        if not getattr(module, "__version__", None) or not getattr(
            module, "__author__", None
        ):
            logger.warning("Hook %s skipped: missing __version__/__author__", name)
            return None

        meta = {field: getattr(module, field, None) for field in META_FIELDS}
        enabled = self._states.get(name)
        if enabled is None:
            enabled = (meta.get("__state__") or "enabled") != "disabled"
        return Hook(
            name=name,
            module=module,
            path=path,
            meta=meta,
            enabled=bool(enabled),
            family=family,
        )

    def _load_imported(self, module_name: str) -> Hook | None:
        """Load a third-party hook from an importable module name."""
        try:
            module = importlib.import_module(module_name)
        except Exception:
            logger.exception("Failed to import hook module %s", module_name)
            return None
        path = getattr(module, "__file__", None) or module_name
        return self._build_hook(module_name, module, str(path), "third")

    def reload(self) -> None:
        """Rebuild the hook snapshot; keep the old one if every load fails."""
        self._states = self._read_states()
        self._imported = self._read_imported()
        hooks: dict[str, Hook] = {}
        for name, file in self._iter_sources():
            try:
                hook = self._load(name, file)
            except Exception:
                logger.exception("Failed to load hook %s", name)
                continue
            if hook is not None:
                hooks[name] = hook
        for module_name in self._imported:
            if module_name in hooks:
                continue
            hook = self._load_imported(module_name)
            if hook is not None:
                hooks[hook.name] = hook

        with self._lock:
            if hooks or not self._hooks:
                self._hooks = hooks
                self._manifests.clear()
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
                "family": hook.family,
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

    # -- declarative UI ------------------------------------------------
    def _build_manifest(self, hook: Hook) -> dict:
        """Validated manifest of one hook, cached until the next reload."""
        cached = self._manifests.get(hook.name)
        if cached is not None:
            return cached

        raw = getattr(hook.module, "hook_manifest", None)
        data = {}
        if callable(raw):
            try:
                data = raw() or {}
            except Exception:
                logger.exception("Hook %s.hook_manifest failed", hook.name)
                data = {}
        if not isinstance(data, dict):
            data = {}

        entry = {
            "name": hook.name,
            "title": str(data.get("title") or hook.meta.get("__hookname__") or hook.name),
            "catalog": data.get("catalog") or hook.meta.get("__catalog__") or "",
            "description": data.get("description")
            or hook.meta.get("__description__")
            or "",
            "author": str(hook.meta.get("__author__") or ""),
            "version": str(hook.meta.get("__version__") or ""),
            "enabled": hook.enabled,
            "family": hook.family,
            "ui_version": ui.UI_VERSION,
            "config_schema": ui.clean_fields(data.get("config_schema")),
            "actions": ui.clean_actions(data.get("actions")),
            "data_sources": ui.clean_sources(data.get("data_sources")),
            "slots": ui.clean_slots(data.get("slots")),
        }
        with self._lock:
            self._manifests[hook.name] = entry
        return entry

    def manifest(self, name: str):
        """Manifest of a single hook, ``None`` when it is not loaded."""
        hook = self.hooks.get(name)
        if hook is None:
            return None
        return self._build_manifest(hook)

    def manifests(self, slots=None) -> list[dict]:
        """Manifests of every loaded hook, optionally filtered to ``slots``."""
        allowed = set(slots) if slots is not None else None
        items = []
        for name in sorted(self.hooks):
            entry = dict(self._build_manifest(self.hooks[name]))
            if allowed is not None:
                entry["slots"] = [
                    slot for slot in entry["slots"] if slot["name"] in allowed
                ]
            items.append(entry)
        return items

    def _hook_config(self, name: str) -> dict:
        """Saved config of one hook (see the hooks page)."""
        try:
            saved = get_setting("hooks_config", {}) or {}
        except Exception:
            logger.exception("Failed to read the config of hook %s", name)
            return {}
        if not isinstance(saved, dict):
            return {}
        data = saved.get(name) or {}
        return dict(data) if isinstance(data, dict) else {}

    def _hook_context(self, name: str, context=None) -> dict:
        """Caller context plus this hook's config, so hooks read one channel."""
        scoped = dict(context or {})
        scoped.setdefault("config", self._hook_config(name))
        return scoped

    def slot(self, name: str, context=None, values=None) -> list[dict]:
        """Render one slot into ``[{hook, title, nodes}]`` blocks."""
        if name not in ui.SLOTS:
            return []
        context = dict(context or {})
        values = dict(values or {})
        blocks = []
        for hook_name in sorted(self.hooks):
            hook = self.hooks[hook_name]
            if not hook.enabled:
                continue
            manifest = self._build_manifest(hook)
            if name not in {slot["name"] for slot in manifest["slots"]}:
                continue
            func = getattr(hook.module, "slot_%s" % name.replace(".", "_"), None)
            if not callable(func):
                logger.warning(
                    "Hook %s declares slot %s without a slot function", hook_name, name
                )
                continue
            hook_context = self._hook_context(hook_name, context)
            try:
                nodes = func(
                    **self._accepted_kwargs(
                        func, dict(context=hook_context, values=values)
                    )
                )
            except Exception:
                logger.exception("Hook %s slot %s failed", hook_name, name)
                continue
            cleaned = ui.clean_tree(
                nodes,
                actions={item["name"] for item in manifest["actions"]},
                values=values,
                context=hook_context,
            )
            if cleaned:
                blocks.append(
                    {"hook": hook_name, "title": manifest["title"], "nodes": cleaned}
                )
        return blocks

    def action(self, name: str, action: str, payload=None, context=None):
        """Run ``action_<action>`` declared by the hook manifest.

        Returns ``None`` when the hook or the action is not declared, so the
        caller can answer 404 instead of reaching into the module.
        """
        hook = self.hooks.get(name)
        if hook is None or not hook.enabled:
            return None
        manifest = self._build_manifest(hook)
        spec = next(
            (item for item in manifest["actions"] if item["name"] == action), None
        )
        if spec is None:
            return None
        func = getattr(hook.module, "action_%s" % action, None)
        if not callable(func):
            return {"code": 1, "message": "action not implemented"}
        payload = dict(payload or {})
        kwargs = dict(
            payload=payload,
            context=self._hook_context(name, context),
            values=dict(payload.get("values") or {}),
        )
        try:
            result = func(**self._accepted_kwargs(func, kwargs))
        except Exception as exc:
            logger.exception("Hook %s action %s failed", name, action)
            result = {"code": 1, "message": str(exc)}
        return ui.clean_result(result)

    def data(self, name: str, source: str, query=None, context=None) -> dict:
        """Read one declared dataset; failures degrade to an empty list."""
        hook = self.hooks.get(name)
        if hook is None or not hook.enabled:
            return {"items": [], "total": 0}
        manifest = self._build_manifest(hook)
        if source not in {item["name"] for item in manifest["data_sources"]}:
            return {"items": [], "total": 0}
        func = getattr(hook.module, "data_%s" % source, None)
        if not callable(func):
            logger.warning("Hook %s declares data source %s without a reader", name, source)
            return {"items": [], "total": 0}
        kwargs = dict(
            query=dict(query or {}),
            context=self._hook_context(name, context),
        )
        try:
            result = func(**self._accepted_kwargs(func, kwargs))
        except Exception:
            logger.exception("Hook %s data source %s failed", name, source)
            return {"items": [], "total": 0}
        return ui.clean_dataset(result)


def init_app(app) -> None:
    from pathlib import Path as _Path

    paths = [_Path(__file__).resolve().parent.parent / "hooks"]
    extra = app.config.get("HOOK_PKG_STORAGE_DIR")
    if extra:
        paths.append(_Path(extra))
    app.extensions["hooks"] = HookManager(
        paths,
        HOOK_RELOAD_TIME,
        state_provider=lambda: get_setting("hooks_state", {}),
        imported_provider=lambda: get_setting("hooks_imported", []),
    )


def get_hook_manager() -> HookManager:
    return current_app.extensions["hooks"]
