# -*- coding: utf-8 -*-
"""
    libs.hook
    ~~~~~~~~~

    As a proxy to dynamically load and unload hook methods.

    :copyright: (c) 2019 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

import warnings
from time import time
from sys import modules
from os import listdir, getpid
from os.path import join, dirname, abspath, isdir, isfile, splitext, basename,\
    getmtime
from jinja2 import ChoiceLoader, FileSystemLoader, PackageLoader
from flask import render_template, render_template_string, Markup, abort, \
    send_from_directory, url_for
from utils.tool import Attribution, is_valid_verion, is_match_appversion, \
    logger, parse_author_mail
from utils._compat import string_types, integer_types, iteritems, text_type, \
    PY2
from config import GLOBAL
from .storage import get_storage


class HookManager(object):

    def __init__(
        self,
        app=None,
        hooks_dir="hooks",
        reload_time=600,
        third_hooks=None,
    ):
        """Receive initialization parameters and
        pass options to :meth:`init_app` method.
        """
        self.__storage = get_storage()
        self.__hf = hooks_dir
        self.__hook_dir = join(dirname(dirname(abspath(__file__))), self.__hf)
        self.__MAX_RELOAD_TIME = int(GLOBAL["HookReloadTime"] or reload_time)
        self.__third_hooks = third_hooks
        self.__last_load_time = time()
        #: hook static endpoint and url_path
        self.__static_endpoint = "assets"
        self.__static_url_path = "/{}".format(self.__static_endpoint)
        #: local and thirds hooks data
        self.__hooks = {}
        #: Initialize app via a factory
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        self.__init_load_hooks()
        #: Register template variable
        app.jinja_env.globals.update(
            intpl=self.call_intpl,
            get_call_list=self.get_call_list,
            emit_assets=self.emit_assets,
            es=self.emit_assets,
        )
        #: Custom add multiple template folders.
        app.jinja_loader = ChoiceLoader([
            app.jinja_loader,
            FileSystemLoader(self.__get_valid_tpl),
        ])
        #: Add a static rule for plugins
        app.add_url_rule(
            '{}/<hook_name>/<path:filename>'.format(self.__static_url_path),
            endpoint=self.__static_endpoint,
            view_func=self._send_static_file,
        )
        #: register extension with app
        app.extensions = getattr(app, 'extensions', None) or {}
        app.extensions['hookmanager'] = self
        self.app = app

    @property
    def _pid(self):
        return str(getpid())

    @property
    def __last_load_time(self):
        hlt = self.__storage.get("hookloadtime") or {}
        return hlt.get(self._pid)

    @__last_load_time.setter
    def __last_load_time(self, timestamp):
        if not isinstance(timestamp, (integer_types, float)):
            raise TypeError("The value of last_load_time type error")
        hlt = self.__storage.get("hookloadtime") or {}
        if timestamp == 0:
            hlt = {k: 0 for k, v in iteritems(hlt)}
        else:
            hlt[self._pid] = timestamp
        self.__storage.set("hookloadtime", hlt)

    @__last_load_time.deleter
    def __last_load_time(self):
        if "hookloadtime" in self.__storage.list:
            del self.__storage['hookloadtime']

    def __del__(self):
        del self.__last_load_time

    def __ensure_reloaded(self):
        hlt = self.__storage.get("hookloadtime") or {}
        myself = hlt.get(self._pid)
        if not myself or (time() - myself) > self.__MAX_RELOAD_TIME:
            self.__hooks = {}
            self.__last_load_time = time()

    @property
    def __third_hooks(self):
        return self.__storage.get("hookthirds") or []

    @__third_hooks.setter
    def __third_hooks(self, third_hook_module_name):
        """添加/删除第三方钩子

        :param str,list third_hook_module_name: 模块名
        """
        if not third_hook_module_name:
            return
        hooks = set(self.__storage.get("hookthirds") or [])
        if isinstance(third_hook_module_name, string_types):
            if third_hook_module_name.endswith(":delete"):
                delete_name = third_hook_module_name.split(":")[0]
                if delete_name in hooks:
                    hooks.remove(delete_name)
            else:
                hooks.add(third_hook_module_name)
        elif isinstance(third_hook_module_name, (list, tuple)):
            hooks.update(third_hook_module_name)
        self.__storage.set("hookthirds", list(set(hooks)))

    def __get_state_storage(self, name):
        s = set(self.__storage.get("hookstate") or [])
        d = "DISABLED.%s" % name
        e = "ENABLED.%s" % name
        if e in s:
            return 'enabled'
        elif d in s:
            return 'disabled'
        else:
            return None

    def __get_state(self, h):
        s = self.__get_state_storage(h.name)
        if s is None:
            s = h.state
        return s

    def __set_state_storage(self, name, state):
        s = set(self.__storage.get("hookstate") or [])
        d = "DISABLED.%s" % name
        e = "ENABLED.%s" % name
        if state == "disabled":
            if e in s:
                s.remove(e)
            s.add(d)
        elif state == "enabled":
            if d in s:
                s.remove(d)
            s.add(e)
        self.__storage.set("hookstate", list(s))

    def __get_fileorparent(self, obj, ask_dir=False):
        py = abspath(obj.__file__.replace(".pyc", ".py"))
        return dirname(py) if ask_dir else py

    def __init_load_hooks(self):
        self.__scan_local()
        self.__scan_third()

    def __scan_local(self):
        if isdir(self.__hook_dir):
            for f in listdir(self.__hook_dir):
                fn, fs = splitext(basename(f))
                fa, fm = join(self.__hook_dir, f), "%s.%s" % (self.__hf, fn)
                if isfile(fa) and fn != "__init__" and fs == ".py":
                    if fm in modules:
                        #: The mtime timestamp of the file when the module
                        #: was first imported.
                        if getattr(modules[fm], '__mtime__', 0) < getmtime(fa):
                            del modules[fm]
                    try:
                        fo = __import__(fm, fromlist=[self.__hook_dir])
                    except ImportError as e:
                        logger.error(e, exc_info=True)
                        continue
                    if hasattr(fo, "__version__") and \
                            hasattr(fo, "__author__"):
                        fo.__mtime__ = getmtime(fa)
                        fo.__family__ = "local"
                        self.__hooks[fm] = self.__get_meta(fo)

    def __scan_third(self):
        if self.__third_hooks and isinstance(self.__third_hooks, list):
            for hn in self.__third_hooks:
                #: hn: the name of the hook module that can be imported
                if hn in modules:
                    hm = modules[hn]
                    if getattr(hm, '__mtime__', 0) < getmtime(
                        self.__get_fileorparent(hm)
                    ):
                        del modules[hn]
                try:
                    ho = __import__(hn)
                except ImportError as e:
                    logger.error(e, exc_info=True)
                    continue
                if hasattr(ho, "__version__") and hasattr(ho, "__author__"):
                    #: 语义化版本号
                    if not is_valid_verion(ho.__version__):
                        warnings.warn("%s: irregular version number" % hn)
                        continue
                    #: 匹配扩展要求的应用版本
                    appversion = getattr(ho, "__appversion__", None)
                    if not is_match_appversion(appversion):
                        warnings.warn(
                            "%s: app version number does not match for %s"
                            % (hn, appversion)
                        )
                        continue
                    ho.__mtime__ = getmtime(self.__get_fileorparent(ho))
                    ho.__family__ = "third"
                    ho.__module_name__ = hn
                    self.__hooks[hn] = self.__get_meta(ho)

    def __get_meta(self, f_obj):
        #: 钩子友好的可见名，非模块名
        name = getattr(
            f_obj, "__hookname__", f_obj.__name__.split('.')[-1],
        )
        state = self.__get_state_storage(name)
        if state is None:
            state = getattr(f_obj, "__state__", "enabled")
        (author, mail) = parse_author_mail(f_obj.__author__)
        return Attribution({
            "author": author,
            "email": mail,
            "version": f_obj.__version__,
            "appversion": getattr(f_obj, "__appversion__", None),
            "description": getattr(f_obj, "__description__", None),
            "state": state,
            "name": name,
            "proxy": f_obj,
            "time": time(),
            "catalog": getattr(f_obj, "__catalog__", None),
            "tplpath": join(self.__get_fileorparent(f_obj, True), "templates"),
            "atspath": join(self.__get_fileorparent(f_obj, True), "static"),
        })

    @property
    def __get_valid_tpl(self):
        return [
            h.tplpath
            for h in self.get_all_hooks
            if isdir(h.tplpath)
        ]

    @property
    def get_all_hooks(self):
        """Get all hooks, enabled and disabled, returns list"""
        self.__ensure_reloaded()
        if not self.__hooks:
            self.__init_load_hooks()
        try:
            hooks = self.__hooks.values()
            data = []
            for h in hooks:
                h["state"] = self.__get_state(h)
                data.append(h)
        except RuntimeError:
            return self.get_all_hooks
        else:
            return data

    @property
    def get_all_hooks_for_api(self):
        """query hook for admin api"""
        hooks = self.get_all_hooks
        return [
            dict(
                name=h.name,
                description=h.description,
                version=h.version,
                appversion=h.appversion,
                author=h.author,
                email=h.email,
                catalog=h.catalog,
                state=h.state,
                ltime=h.time,
                mtime=h.proxy.__mtime__,
                family=h.proxy.__family__,
            )
            for h in hooks
        ]

    @property
    def get_map_hooks(self):
        """Get all hooks, enabled and disabled, returns dict"""
        return {h.name: h for h in self.get_all_hooks}

    @property
    def get_enabled_hooks(self):
        """Get all enabled hooks, return list"""
        return [
            h
            for h in self.get_all_hooks
            if h.state == 'enabled'
        ]

    @property
    def get_enabled_map_hooks(self):
        """Get map enabled hooks, return dict"""
        return {
            name: h
            for name, h in iteritems(self.get_map_hooks)
            if h.state == 'enabled'
        }

    def disable(self, name):
        """禁用钩子"""
        if name in self.get_map_hooks:
            self.__set_state_storage(name, "disabled")

    def enable(self, name):
        """启用钩子"""
        if name in self.get_map_hooks:
            self.__set_state_storage(name, "enabled")

    def reload(self):
        self.__hooks = {}
        self.__last_load_time = 0
        self.__init_load_hooks()

    def add_third_hook(self, third_hook_module_name):
        """添加第三方钩子

        :param str third_hook_module_name: 钩子可直接导入的模块名
        """
        if third_hook_module_name:
            self.__third_hooks = third_hook_module_name
            if hasattr(self, 'app'):
                self.app.jinja_loader.loaders.append(
                    PackageLoader(third_hook_module_name)
                )
            self.reload()

    def remove_third_hook(self, third_hook_name):
        """移除第三方钩子

        :param str third_hook_name: 钩子名（非模块名）
        """
        if third_hook_name:
            p = self.proxy(third_hook_name, is_enabled=False)
            if p and p.__family__ == "third" and hasattr(p, "__module_name__"):
                self.__third_hooks = "%s:delete" % p.__module_name__
                self.reload()

    def proxy(self, name, is_enabled=True):
        """代理到钩子中执行方法

        :param str name: 钩子名称（__hookname__），非其模块名
        :param bool is_enabled: True表示仅从已启用钩子中查找方法，否则查找所有
        """
        if is_enabled:
            if name in self.get_enabled_map_hooks:
                return self.get_enabled_map_hooks[name]["proxy"]
        else:
            if name in self.get_map_hooks:
                return self.get_map_hooks[name]["proxy"]

    def get_call_list(
        self, _callname, _include=None, _exclude=None, _type='all'
    ):
        """获取所有启用钩子的某个类型对应的方法/变量"""
        hooks = []
        for h in sorted(self.get_enabled_hooks, key=lambda h: h.name):
            if _include and isinstance(_include, (tuple, list)):
                if h.name not in _include:
                    continue
            if _exclude and isinstance(_exclude, (tuple, list)):
                if h.name in _exclude:
                    continue
            hin = False
            tpl = getattr(h.proxy, "intpl_%s" % _callname, None)
            cn = getattr(h.proxy, _callname, None)
            if _type == "func":
                if callable(cn):
                    hin = True
            elif _type == "tpl":
                if tpl:
                    hin = True
            elif _type == "bool":
                if cn is True:
                    hin = True
            else:
                if callable(cn) or tpl:
                    hin = True
            if hin:
                if PY2 and h.description:
                    if not isinstance(h.description, text_type):
                        h["description"] = h.description.decode("utf-8")
                hooks.append(dict(name=h.name, description=h.description))
        return hooks

    def call(
        self,
        _funcname,
        _include=None,
        _exclude=None,
        _every=None,
        _mode=None,
        _args=None,
        _kwargs=None,
    ):
        """Try to execute the func method in all enabled hooks.

        .. versionchanged:: 1.7.0
            add param `_mode` and `_every`

        .. versionchanged:: 1.9.0
            _mode add any_false

        .. deprecated:: 1.8.0
            _callback replaced by `_every`;
            args replaced by `_args`;
            kwargs replaced by `_kwargs`
        """
        response = []
        for h in sorted(self.get_enabled_hooks, key=lambda h: h.name):
            if _include and isinstance(_include, (tuple, list)):
                if h.name not in _include:
                    continue
            if _exclude and isinstance(_exclude, (tuple, list)):
                if h.name in _exclude:
                    continue
            func = getattr(h.proxy, _funcname, None)
            if callable(func):
                try:
                    if isinstance(_args, (list, tuple)) and \
                            isinstance(_kwargs, dict):
                        result = func(*_args, **_kwargs)
                    elif isinstance(_kwargs, dict):
                        result = func(**_kwargs)
                    elif isinstance(_args, (list, tuple)):
                        result = func(*_args)
                    else:
                        result = func()
                except (ValueError, TypeError, Exception) as e:
                    result = dict(code=1, msg=str(e))
                else:
                    if isinstance(result, dict):
                        if "code" not in result:
                            result["code"] = 0
                    else:
                        result = dict(code=0, data=result)

                result["sender"] = h.name
                #: Use `_every` to change the hook execution result
                if callable(_every):
                    r = _every(result)
                    if isinstance(r, dict) and "code" in r:
                        if "sender" not in r:
                            r["sender"] = h.name
                        result = r
                response.append(result)

                if _mode == "any_true":
                    #: 任意钩子处理成功时则中止后续
                    if result.get("code") == 0:
                        break

                elif _mode == "any_false":
                    #: 任意钩子处理失败时则中止后续
                    if result.get("code") != 0:
                        break

        return response

    def call_intpl(self, _tplname, _include=None, _exclude=None, **context):
        """在模板中渲染

        :param _tplname: 扩展点名称
        :param list _include: 仅查找哪些钩子
        :param list _exclude: 排除哪些钩子
        :kerword context: 渲染模板时传递的变量
        :type _tplname: str or function
        :returns: Markup HTML
        """
        result = []
        for h in sorted(self.get_enabled_hooks, key=lambda h: h.name):
            if _include and isinstance(_include, (tuple, list)):
                if h.name not in _include:
                    continue
            if _exclude and isinstance(_exclude, (tuple, list)):
                if h.name in _exclude:
                    continue
            #: tpl is a file or html code or a func
            tpl = getattr(h.proxy, "intpl_%s" % _tplname, None)
            if not tpl:
                continue
            if callable(tpl):
                tpl = tpl()
            if tpl.split(".")[-1] in ("html", "htm", "xhtml"):
                content = render_template(tpl, **context)
            else:
                if PY2 and not isinstance(tpl, text_type):
                    tpl = tpl.decode("utf-8")
                content = render_template_string(tpl, **context)
            if content:
                result.append(content)
        return Markup("".join(result))

    def _send_static_file(self, hook_name, filename):
        try:
            h = self.get_enabled_map_hooks[hook_name]
        except KeyError:
            return abort(404)
        else:
            return send_from_directory(h.atspath, filename)

    def emit_assets(self, hook_name, filename, _raw=False, _external=False):
        """在模板中快速构建出扩展中静态文件的地址。

        当然，可以用 :func:`flask.url_for` 代替。

        如果文件以 `.css` 结尾，那么将返回 `<link>` ，例如::

            <link rel="stylesheet" href="/assets/hook/hi.css">

        如果文件以 `.js` 结尾，那么将返回 `<script>` ，例如::

            <script type="text/javascript" src="/assets/hook/hi.js"></script>

        其他类型文件，仅仅返回文件地址，例如::

            /assets/hook/img/logo.png
            /assets/hook/attachment/test.zip

        以下是一个完整的使用示例：

        .. code-block:: html

            <!DOCTYPE html>
            <html>
            <head>
                <title>Hello World</title>
                {{ emit_assets('demo','css/demo.css') }}
            </head>
            <body>
                <div class="logo">
                    <img src="{{ emit_assets('demo', 'img/logo.png') }}">
                </div>
                <div class="showJsPath">
                    <scan>
                        {{ emit_assets('demo', 'js/demo.js', _raw=True) }}
                    </scan>
                </div>
            </body>
            </html>

        :param hook_name: 钩子名

        :param path filename: 钩子包下static目录中的文件

        :param bool _raw: True则只生成文件地址，不解析css、js，默认False

        :param bool _external: 转发到url_for的_external

        :returns: html code with :class:`~flask.Markup`

        .. versionadded:: 1.9.0
        """
        uri = url_for(
            self.__static_endpoint,
            hook_name=hook_name,
            filename=filename,
            _external=_external,
        )
        if _raw is not True:
            if filename.endswith(".css"):
                uri = '<link rel="stylesheet" href="%s">' % uri
            elif filename.endswith(".js"):
                uri = '<script type="text/javascript" src="%s"></script>' % uri
        return Markup(uri)
