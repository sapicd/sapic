# 开发与贡献

## 目录结构

```text
server/                 v2 后端（包名 sapic，纯本地包，不发布 PyPI）
├── requirements/       base / dev / prod / hooks 四组依赖
└── sapic/
    ├── __init__.py     create_app() 工厂
    ├── cli.py          flask sa 命令（upgrade / create-admin / purge-expired）
    ├── basis/          配置、异常、常量、DB/Redis 连接（不依赖业务）
    ├── libs/           通用基类与封装：auth / images / albums / storage / users / mail / settings / hook / ext / ui
    ├── utils/          common.py（纯工具）、web.py（依赖 Flask 上下文）
    ├── views/          蓝图与路由，薄封装
    ├── models/         Peewee 模型
    ├── migrations/     幂等迁移，启动时自动执行
    └── hooks/          内置钩子，一个 .py 即一个插件
web/                    v2 前端（Vue 3 + Vite + Element Plus）
docs/                   本文档（Sphinx + MyST）
tools/                  v1 → v2 数据迁移脚本
V1/                    v1 存档，不参与构建
```

依赖方向单向：`views → libs/utils → models/basis`。`utils/web.py` 依赖 Flask 上下文，
不能被非 Web 模块导入；钩子只被 `libs/hook.py` 按需导入，禁止反向依赖业务层。

| 内容 | 位置 |
| --- | --- |
| 配置、异常、常量 | `basis/` |
| DB / Redis 连接 | `basis/db.py` |
| 通用基类与功能封装 | `libs/` |
| 纯工具（无 Web 上下文） | `utils/common.py` |
| 依赖 `request` / `g` 的函数 | `utils/web.py` |
| 路由与薄封装 | `views/` |
| 扩展契约判断 | `libs/ext.py` |

## 常用命令

```bash
make setup          # 后端 dev.txt + 前端 pnpm install
make dev            # 0.0.0.0:9514，自动重载（自带 sapic_env=dev）
make test           # 后端 pytest
make web-dev        # 前端 127.0.0.1:5173
make web-build      # 前端构建到 web/dist
make upgrade        # 手动兜底迁移
make create-admin U=admin P='密码'
make docs           # 构建本文档到 docs/_build/html
```

变量可覆盖：`make dev PORT=8080`、`make serve WORKERS=8`。

## 测试

- 后端用 pytest，测试在 `server/tests/`，`cd server && python -m pytest -q`。
- 测试用临时 SQLite，不依赖外部数据库与 Redis；CI 跑 Python 3.10 与 3.12。
- 新增扩展契约、解析、权限判定时应补对应单测：

```bash
cd server && python -m pytest -q tests/test_ext.py       # 扩展点契约
cd server && python -m pytest -q tests/test_auth_oidc.py # 登录 Provider 流程
cd server && python -m pytest -q tests/test_api_backends.py
```

## 文档

本文档用 Sphinx + MyST（Markdown）编写，配置在 `docs/conf.py`：

```bash
make docs                       # 等价于 pip install -r docs/requirements.txt && sphinx-build
cd docs && make html            # 只构建
cd docs && make linkcheck       # 检查外链
```

- 新增页面后在 `docs/index.md` 的 `toctree` 里登记，否则不会被构建。
- CI 用 `-W` 构建，warning 即失败；改动文档后本地跑一次 `make docs`。
- 站点托管在 Read the Docs（`.readthedocs.yaml`），GitHub Actions 也会构建并发布到 Pages。

## 代码风格

- PEP 8，4 空格缩进，文件头 `# -*- coding: utf-8 -*-` + 模块 docstring（英文职责描述）。
- 导入顺序：标准库 → 第三方 → 项目内，组间空行，全部放文件头部。
- Python 3.10+ 语法，新增函数带类型注解（`str | None`、`dict[str, Any]`）。
- 业务失败用 `ApiError(message, code)`（英文消息），不要裸返回 dict；不要裸 `except:`。
- 日志用 `logging.getLogger(__name__)`，禁止 `print()`。
- 数据库结构变更走 `migrations/` 的幂等迁移，不要直接 `create_tables()` 改线上结构。
- 新增配置项必须同时接进「后台表单 + 实际生效点」。
