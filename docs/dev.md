# 开发与贡献

## 目录结构

```text
server/                 v2 backend (package sapic, local only, not on PyPI)
├── requirements/       three groups: base / dev / prod
└── sapic/
    ├── __init__.py     create_app() factory
    ├── cli.py          flask sa commands (upgrade / create-admin / purge-expired / review-pending / scheduler)
    ├── basis/          config, errors, constants, DB connection (no business deps)
    ├── libs/           shared base classes: auth / images / albums / storage / users / mail / settings / hook / ext / ui
    ├── utils/          common.py (plain helpers), web.py (needs a Flask context)
    ├── views/          blueprints and routes, thin wrappers
    ├── models/         Peewee models
    ├── migrations/     idempotent migrations, run at startup
    └── hooks/          built-in hooks; one .py is one plugin
web/                    v2 front end (Vue 3 + Vite + Element Plus)
docs/                   these docs (Sphinx + MyST)
tools/                  v1 -> v2 data migration script
```

依赖方向单向：`views → libs/utils → models/basis`。`utils/web.py` 依赖 Flask 上下文，
不能被非 Web 模块导入；钩子只被 `libs/hook.py` 按需导入，禁止反向依赖业务层。

写扩展（存储驱动 / 登录 Provider / 界面钩子）的契约、最小样例与本地联调见[扩展开发](extend/index.md)。

| 内容 | 位置 |
| --- | --- |
| 配置、异常、常量 | `basis/` |
| DB 连接 | `basis/db.py` |
| 通用基类与功能封装 | `libs/` |
| 纯工具（无 Web 上下文） | `utils/common.py` |
| 依赖 `request` / `g` 的函数 | `utils/web.py` |
| 路由与薄封装 | `views/` |
| 扩展契约判断 | `libs/ext.py` |

## 常用命令

```bash
make setup          # backend dev.txt + front-end pnpm install
make dev            # 0.0.0.0:9514, auto reload (sets sapic_env=dev)
make test           # backend pytest
make web-dev        # front end on 127.0.0.1:5173
make web-build      # build the front end into web/dist
make upgrade        # manual migration fallback
make create-admin U=admin P='password'
make docs           # build these docs into docs/_build/html
```

变量可覆盖：`make dev PORT=8080`、`make serve WORKERS=8`。

```{note}
上面这些是 `Makefile` 的封装，只图本地少敲字：它们假定仓库根的 `.venv` 存在、机器上有 `make`。
CI、容器与生产环境通常没有 `make`，请直接用真实命令——安装与启动见[安装与部署](install.md)，
生产部署的完整命令见[部署与运维](deploy.md)。

`make dev` 自己会带 `sapic_env=dev`（DEBUG + 详细日志）；`config` / `upgrade` / `create-admin`
不带，用的是默认配置——没有 `server/.cfg` 也能直接跑，需要开发默认值时自己加 `sapic_env=dev`。
```

## 测试

- 后端用 pytest，测试在 `server/tests/`，`cd server && python -m pytest -q`。
- 测试用临时 SQLite，不依赖外部数据库；CI 跑 Python 3.10 与 3.12。
- 新增扩展契约、解析、权限判定时应补对应单测：

```bash
cd server && python -m pytest -q tests/test_ext.py       # extension contracts
cd server && python -m pytest -q tests/test_auth_oidc.py # login provider flow
cd server && python -m pytest -q tests/test_api_backends.py
```

## 文档

本文档用 Sphinx + MyST（Markdown）编写，配置在 `docs/conf.py`：

```bash
make docs                       # same as pip install -r docs/requirements.txt && sphinx-build
cd docs && make html            # build only
cd docs && make html-en         # build English from the locale/en translations
cd docs && make update-po       # sync .po entries after editing Chinese
cd docs && make linkcheck       # check external links
```

- 新增页面后在 `docs/index.md` 的 `toctree` 里登记，否则不会被构建。
- `make docs` 自带 `-W`（warning 即失败）；改动文档后本地跑一次再提交。
- 线上站点由 Read the Docs 构建（`.readthedocs.yaml`，`fail_on_warning: true`），
  仓库里不再有发布文档的 GitHub Actions。
- **文档是双语的**：中文是源语言，英文译文在 `docs/locale/en/LC_MESSAGES/*.po`（每页一个）。
  改完中文跑 `cd docs && make update-po`，把新增/变动的条目补上 `msgstr` 即可；
  没译的条目构建英文站时自动回落中文，所以可以分批翻。代码块不参与抽取，
  示例里的注释直接用英文写。新增页面要同时生成对应的 `.po`。
- 英文站要在 RTD 后台新建一个翻译项目（语言 `en`）并关联到主项目，语言切换器由 RTD 提供，
  代码侧不需要额外配置；`docs/locale/en` 里的 `.po` 是唯一的译文来源。

## 代码风格

- PEP 8，4 空格缩进，文件头 `# -*- coding: utf-8 -*-` + 模块 docstring（英文职责描述）。
- 导入顺序：标准库 → 第三方 → 项目内，组间空行，全部放文件头部。
- Python 3.10+ 语法，新增函数带类型注解（`str | None`、`dict[str, Any]`）。
- 业务失败用 `ApiError(message, code)`（英文消息），不要裸返回 dict；不要裸 `except:`。
- 日志用 `logging.getLogger(__name__)`，禁止 `print()`。
- 数据库结构变更走 `migrations/` 的幂等迁移，不要直接 `create_tables()` 改线上结构。
- 新增配置项必须同时接进「后台表单 + 实际生效点」。
