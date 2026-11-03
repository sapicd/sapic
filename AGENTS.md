# sapic (v2) — 项目上下文

sapic 是一个自建图床，**v2 是 API-only 的 Flask 后端 + 独立 Vue 前端**，
**ORM 用 Peewee**（不再是 v1 的纯 Redis 存储），**存储后端与扩展点完全插件化（钩子体系）**。
v1 代码已归档在 `V1/`，仅供对照，不参与 v2 构建；v1 的项目约定见 `V1/AGENTS.md`。
当前版本见 `server/sapic/version.py` 中的 `__version__`。

技术栈（后端）：Python 3.10+，Flask，Peewee，Redis，psycopg(binary)，PyMySQL，PyJWT。
前端：`web/` 是独立的 Vue 3 + Vite + Element Plus 应用，与后端通过 `/api` 与 `/i/` 交互。
详细架构见 `ARCH.md`，贡献流程见 `CONTRIBUTING.md`。

> Python 版本下限是 **3.10**，可自由使用 3.10 语法（`X | Y` 联合类型、match 语句、内置泛型
> `dict[str]` 等）。新增代码统一带类型注解，与既有 `sapic/` 模块风格一致。

## 目录结构

后端在 `server/`，包名 `sapic`，是**纯本地包**（不发布 PyPI、也不做 `pip install`）。
命令均在 `server/` 下执行，`cwd` 已在 `sys.path`，可直接 `import sapic`；依赖由仓库根
`requirements/` 管理（base/dev/prod），装在仓库根的 `.venv/`，不要手动 `activate`。

```
.
├── server/               v2 后端（包名 sapic，纯本地包，不发布 PyPI）
│   ├── pyproject.toml    仅 pytest 等本地工具配置（依赖见 requirements/）
│   ├── .gitignore
│   ├── sapic/            v2 后端包（import sapic）
│   │   ├── __init__.py   create_app() 工厂
│   │   ├── version.py    __version__
│   │   ├── cli.py        flask sa 命令入口（upgrade / create-admin）
│   │   ├── basis/        基础设施层（不依赖业务）
│   │   │   ├── common.py 通用基础函数：as_bool / as_int / is_dev
│   │   │   ├── conf.py   配置类 BaseConfig/DevConfig/ProdConfig + load_config()
│   │   │   ├── db.py     Peewee 数据库 / Redis 连接封装
│   │   │   ├── errors.py ApiError / ErrorCode / 错误处理注册
│   │   │   └── vars.py   常量：BASE_DIR / ENV_PREFIX / LOG_LEVEL_TYPE / 会话与文档地址
│   │   ├── libs/         通用基类、接口类与功能封装（auth/images/albums/storage/users/mail/settings）
│   │   │   ├── auth.py   会话 / PAT / CSRF 与权限装饰器
│   │   │   ├── hook.py   HookManager：清单 / 插槽 / 动作 / 数据集
│   │   │   └── ui.py     声明式 UI 词表与清洗（唯一可信来源）
│   │   ├── utils/
│   │   │   ├── common.py 纯工具函数（不依赖 Flask 上下文，如游标编解码）
│   │   │   └── web.py    Web 工具（依赖 Flask 上下文：响应信封、分页）
│   │   ├── views/        Flask 蓝图与路由（auth/settings/users/uploads/images/albums/health/public/hooks）
│   │   ├── models/       Peewee 模型（BaseModel）
│   │   ├── migrations/   Peewee 迁移框架（flask sa 命令入口）
│   │   └── hooks/        内置钩子，一个 .py 即一个插件（up2local 等）
│   └── tests/            pytest 测试（test_*.py，pyproject 的 testpaths=["tests"]）
├── web/                  v2 前端（Vue 3 + Vite + Element Plus）
├── V1/                   v1 旧代码与文档，仅存档
├── requirements/             依赖：base.txt（运行时）/ dev.txt（开发+测试）/ prod.txt（部署）
├── Makefile              常用命令入口
└── README.md
```

依赖方向单向：`views → libs/utils → models/basis`；`utils/web.py` 依赖 Flask 上下文，
禁止被非 Web 模块导入；`libs/hook` 依赖 `libs/ui` 做节点清洗；
钩子（`server/sapic/hooks/*`）只被 `libs/hook` 按需导入，禁止反向依赖业务层。

代码按职责放到固定位置，禁止错位：

| 内容 | 位置 |
|------|------|
| 配置、异常、常量、最基础依赖 | `basis/`（`conf.py` / `errors.py` / `vars.py` / `common.py`） |
| 数据库 / Redis 连接封装 | `basis/db.py` |
| 通用基类、接口类、封装功能类 | `libs/`（auth/images/storage/users/mail/settings/hook/ui） |
| 纯工具函数（无 Web 上下文） | `utils/common.py` |
| 依赖 `request` / `g` / `jsonify` 的函数 | `utils/web.py` |
| 视图（蓝图、路由、装饰器与薄封装） | `views/` |

## 常用命令

```bash
make setup            # 安装开发依赖（后端 dev.txt + 前端 pnpm install）
make setup-hooks      # 钩子可选依赖 (requirements/hooks.txt：requests/pillow/qiniu/upyun)
make install-prod     # 生产部署依赖 (requirements/prod.txt：base + gunicorn + gevent)
make config           # 打印当前生效配置 (python -c load_config)
make upgrade          # 手动兜底：建表 / 增量迁移（启动时已自动执行）
make create-admin     # 创建管理员，需 U=admin P='密码'
make dev              # 开发服务器 0.0.0.0:9514 (flask run --reload，改代码自动重启)
make serve            # gunicorn 前台运行 (WORKERS=4 -k gevent)
make test             # 后端 pytest
make web-dev          # 前端开发服务器 127.0.0.1:5173（/api 与 /i/ 代理到 9514）
make web-build        # 前端构建到 web/dist
make clean            # 清理缓存与构建产物
```

变量可覆盖：`make dev PORT=8080`、`make serve WORKERS=8`。`make` 无参数即打印帮助。

## Python 编码规范

### 基本风格

- 遵循 **PEP 8**，缩进 4 空格，不使用 Tab，文件末尾保留一个空行
- 行宽与既有代码保持一致（约 100 字符，匹配 `sapic/` 现状）
- 文件头固定写法：`# -*- coding: utf-8 -*-` + 三引号模块 docstring（英文职责描述）

```python
# -*- coding: utf-8 -*-
"""sapic.libs.ui

Declarative UI vocabulary for hook front-ends.
"""
```

### 导入顺序

按以下顺序分组，组间空一行（工具会校验）：

1. 标准库（`os`, `json`, `time`...）
2. 第三方库（`flask`, `peewee`, `redis`...）
3. 项目内部（`sapic.xxx` / `..xxx` 相对导入）

风格要点：

- 每个模块单独一行，同组字母序；新模块插到合适位置，不要追加在文件末尾
- 所有 `import` 放文件头部，禁止在函数内导入模块（循环导入用 `current_app` 延后取资源）
- 同一包内可用相对导入（`from . import ui`），跨包一律绝对导入（`from sapic.libs import ui`）

```python
# 正确示例
import json
from pathlib import Path

from flask import current_app

from sapic.basis.errors import ApiError
from sapic.libs import ui
```

### 命名规范

| 类型 | 风格 | 示例 |
|------|------|------|
| 模块/文件 | snake_case | `up2local.py`, `hook.py` |
| 类 | PascalCase | `HookManager`, `BaseModel` |
| 函数/方法 | snake_case | `load_config()`, `upimg_save()` |
| 变量 | snake_case | `upload_path`, `img_url` |
| 常量 | UPPER_SNAKE_CASE | `UI_VERSION`, `MAX_DEPTH` |
| 私有成员 | 单下划线 | `_manifests`, `_accepted_kwargs` |

### 类型注解

- v2 代码**普遍带注解**，新增函数按 `3.10+` 写法：`str | None`、`dict[str, Any]`
- 修改已有函数时保持其原有风格（带注解的保持带注解）
- 复杂结构可用 `typing` 的 `Optional` / `Dict` / `List`，但优先内置泛型

```python
def manifest(self, name: str) -> dict | None:
    ...
```

### 注释与文档

- 模块级：文件头三引号，含英文职责描述
- 类/函数：docstring 用英文，复杂逻辑注释解释「为什么」而非复述代码
- 行内注释用英文，项目惯用 `#:` 开头作为段落级说明
- 面向用户的可见文案放在后端响应里（见下），不在代码里散落中文提示

### 字符串与格式化

- 优先 `.format()` / f-string；改动某文件时沿用其既有风格
- 拼接路径用 `os.path.join` / `posixpath.join`，不要手拼 `/`
- SQL 由 Peewee ORM 生成，禁止手写拼接 SQL

### 异常处理

- 统一异常：`ApiError(message, code=ErrorCode, status_code)`（`sapic/basis/errors.py`）
- 视图层返回 `ok(data)` 或 `err(...)` / `raise ApiError(...)`，不要裸返回 `dict`
- 禁止裸 `except:`，至少 `except Exception:` 或明确异常元组
- DB / Redis / 第三方 SDK 调用需捕获特定异常并转换为 `ApiError` 或带 `msg` 的失败响应
- 不用 `print()` 打日志，统一用 `logging.getLogger(__name__)`

### API 响应信封 ★

所有 `/api/v2/*` 响应统一由 `sapic/utils/web.py` 的 `ok()` 包裹（错误走 `ApiError`）：

```json
{ "code": "OK", "message": "", "data": { ... } }      // 成功
{ "code": "NOT_FOUND", "message": "xxx", "data": null } // 失败，code 为 ErrorCode 字符串
```

- 业务成功永远 `code: "OK"`；失败 `code` 是 `ErrorCode` 枚举名（如 `UNAUTHORIZED` /
  `FORBIDDEN` / `NOT_FOUND` / `INVALID_ARGUMENT` 等），**不要自己造字符串**
- 业务消息用英文原文；前端负责本地化，不要在后端返回中文 `msg`
- 错误由 `@app.errorhandler(HTTPException)` 统一转成上述信封，视图里直接 `abort(404)` 即可

## 数据库（Peewee）

- 模型集中在 `sapic/models/`，基类 `BaseModel` 已含 `id` / 时间戳等公共字段
- 连接由 `sapic/basis/db.py` 的 `db` 单例管理，配置来自 `load_config()` 的 `DATABASE_URL`
- **结构变更走迁移**：在 `sapic/migrations/` 的 `MIGRATIONS` 注册迁移函数（必须幂等），
  应用启动时由 `auto_upgrade()` 自动执行，`make upgrade` 只作手动兜底；不要直接
  `db.create_tables()` 改线上结构
- 批量操作优先 `atomic()` 事务；查询用 Peewee 表达式，杜绝字符串拼接
- 测试用临时 SQLite（`sapic_db_url=sqlite:///...`），不要依赖具体数据库方言

## 站点设置

- 默认值集中在 `sapic/libs/settings.py` 的 `DEFAULTS`，读写统一走 `get_setting` / `set_setting`
- 后台通过 `GET/PUT /api/v2/settings` 管理（仅管理员），可写键白名单与类型校验在 `views/settings.py`
- 前台展示字段由公开接口 `GET /api/v2/site` 输出，前端在 `stores/site.js` 消费
- 上传类设置（后缀白名单 / 大小 / 数量 / 视频）在 `views/uploads.py` 生效，注册类设置在 `views/auth.py` 生效；
  新增配置项必须同时接入「后台表单 + 实际生效点」，不要留下只存不用的配置
- `password_login`（默认开）关闭后 `views/auth.py` 的登录与注册接口直接 403，登录页只渲染统一登录入口
- 统一登录（OIDC）：`passport` 钩子提供 provider 能力，`views/auth.py` 负责发起/回调与绑定，
  `libs/users.py` 的 `resolve_oidc_user` 处理「已绑定 → 登录 / 双方邮箱均已验证 → 自动关联 / 否则按
  provider 信息建号」（新用户主要入口）；解绑需校验当前密码，避免 OIDC 专用账号锁死自己
- 邮箱验证：注册自动寄令牌，`POST /api/v2/auth/email/verify` 重发、`POST /api/v2/auth/email/confirm`
  提交令牌后置 `email_verified=True`；改邮箱会重置为未验证，且 `resolve_oidc_user` 要求本地已验证
- 后台页面已拆分：`/admin` 站点设置（`AdminView`）、`/admin/hooks` 钩子管理（`HooksView`）、
  `/admin/users` 用户管理（`UsersView`），各自挂 `admin.*` 插槽；不要把它们再合并回一页
- 用户管理走 `GET/PATCH /api/v2/users`（仅管理员，`views/users.py`）：列表支持关键词与状态筛选
  （`-2` 已拒绝 / `-1` 待审核 / `0` 已禁用 / `1` 正常），PATCH 可改 `status` 与 `is_admin`；
  禁用/拒绝会自增 `session_version` 让既有会话失效，且管理员不能改自己的状态或撤销自己的管理员权限

## 相册与可见性 ★

权限以**相册**为维度：每张图片都必须属于一个相册，可见性由相册决定，单张图片可覆盖。

- 上传兜底：`libs/albums.resolve_album(owner)` —— 登录用户落到其**默认相册**
  （`albums.is_default`，新用户注册时创建，可见性取设置 `default_album_visibility`，默认 `public`），
  匿名上传落到**系统相册**（`albums.owner_id` 为 NULL 的「公共相册」）。`create_image()` 内部兜底，
  不要绕过它直接建 `Image`，否则会出现无相册（= 默认可公开）的图片。
- 单图覆盖：`Image.visibility` 为 NULL 表示跟随相册；前端详情页用「跟随相册」选项清空。
- 默认相册不可删除（409）；系统相册对普通用户不可见，管理员在 `GET /api/v2/albums`
  会额外拿到 `role=system` 的那条，用于筛选匿名图片。
- 结构变更走 `sapic/migrations/`：`v002_album_ownership` 负责 `owner_id` 可空、`is_default` 列
  与存量图片回填，必须保持幂等。
- 图片地址（`src`）：公开图直接返回优先级最高副本的直链（钩子 `upimg_save` 返回的 `src`），
  私有图固定走 `/i/<sha>` 由 sapic 鉴权后输出；私有远程副本在 `/i/` 内流式转发，不做 302，
  避免暴露源站地址。没有直链的后端（未配 `domain` 的本地存储）同样回落到 `/i/<sha>`。
- 存储 key 固定为 `{用户}/{年}/{月}/{日}/{ASCII 文件名}-{sha 片段}.{ext}`（`libs.images.upload_path_for` +
  `create_image`），后缀保证同名文件不被覆盖；文件名经 `secure_filename` 清洗，主体被整段清空时用
  `{yyyyMMddHHmmss}{6 位随机}` 兜底（不同中文名不会撞成同一个 `image`），删除按 `object_key` 执行。

## 钩子（插件）开发规范 ★

钩子是**声明式 UI 插件**：它用数据描述自己的配置表单、插槽、动作、数据集，由前端
同一套渲染器消费。后端只做校验与执行，**前端不认识任何插件名**。完整词表见
`sapic/libs/ui.py`（唯一可信来源），端点见 `sapic/views/hooks.py`。

`sapic/hooks/up2local.py` 是参考实现。新增钩子必须满足：

```python
# -*- coding: utf-8 -*-
"""sapic.hooks.up2local — 本地目录存储后端。"""

__version__ = "0.4.0"
__author__ = "staugur"
__description__ = "将图片保存到本地目录"
__catalog__ = "upload"      # 归类，upload 表示存储后端
__state__ = "enabled"       # enabled / disabled
```

要点：

- 必备元数据 `__version__` 与 `__author__`
- **无 import 副作用的模块级代码**：钩子会被反复扫描加载，不要在模块顶层初始化连接
- 存储类钩子实现 `upimg_save(filename, stream, upload_path="", backend=None, **kwargs)`
  （返回 `{"code": 0, "path": <key>, "size": <bytes>, "etag": <hash>}`，并在后端配置了
  「加速域名」`domain` 时附带 `src` 直链；没有 `src` 时服务层回落到 `/i/<sha>`）与
  `upimg_delete(sha, upload_path, filename, basedir, save_result)`（失败不外抛）

### 声明式 UI 契约

`sapic/libs/hook.py` 的 `HookManager` 通过以下约定聚合每个钩子的 UI：

| 钩子函数 | 返回值 | 说明 |
| --- | --- | --- |
| `hook_manifest()` | dict | `{title, catalog, config_schema, actions, data_sources, slots}` |
| `slot_<name>(context=None, values=None)` | list[节点] | 渲染某个插槽的节点树 |
| `action_<name>(payload=None, context=None, values=None)` | dict | `{code, message, toast, refresh}` |
| `data_<name>(query=None, context=None)` | dict | `{items: [...], total: int}` |

- `config_schema` / `actions` / `data_sources` / `slots` 全部经 `sapic/libs/ui.py` 的
  `clean_*` 清洗：未知类型/键被丢弃、`href` 仅允许 `http(s)` 与站内 `/`、
  `action` 必须声明于 manifest，否则被静默忽略（防 XSS / 越权）
- `slots` 的 `name` 必须在 `ui.SLOTS` 白名单内；`admin.*` 开头的插槽仅管理员可见
- 节点类型完整列表见 `ui.py`：`fieldset/group/row/col/tabs/collapse/list/list_item`、
  `text/alert/badge/image/code/divider`、`input/number/password/textarea/switch/select/radio`、
  `button/link/dropdown/dropdown_item`
- `action` 返回里的 `toast` 仅当 `level` 在白名单内才会透传给前端；`refresh=True` 触发前端刷新
- 钩子自带的私有依赖：在 `requirements/` 下加文件并用 `try/except ImportError` 兜底英文提示，
  **不要**在 `requirements/base.txt` 强制引入可选 SDK

## 前端规范（Vue 3 / Element Plus）

- 工程在 `web/`，独立 pnpm 工程；依赖 `pnpm install`，开发 `pnpm run dev`，构建 `pnpm run build`（`make` 会自动检测/安装 pnpm）
- 变量用 `let` / `const`，函数 camelCase，组件 PascalCase，模板用 `<script setup>`
- 全屏背景 / 顶部导航 / 页脚统一由 `layout/AppLayout.vue` 提供（`App.vue` 用 `<slot>` 注入页面），
  站点信息（名称、背景图、注册与匿名上传开关）取 `GET /api/v2/site`（`stores/site.js`），
  未配置背景时回落到 `web/public/background.jpg`；`logo.png` / `favicon.png` 沿用 V1 资源
- **前端不感知插件业务逻辑**：`HookSlot` 按插槽名拉节点树，`NodeRenderer` 递归分发词表，
  未知类型静默跳过（向后兼容）；`icon` 走 `builtin:` / `brand:` 名义映射，`href` 直接使用
  后端已替换好占位符的最终地址，按钮只调用节点自带且后端已校验的 `action`
- 不在 HTML 属性写内联 JS，用户输入渲染前做转义防 XSS
- 统一走 `api/client.js` 的封装（信封解析、CSRF、401 回调、错误归一），不要散落 `fetch`
- Element Plus 按需引入（`unplugin-auto-import` + `unplugin-vue-components`）：模板直接写 `<el-xxx>`，
  脚本直接用 `ElMessage` / `ElMessageBox` 等 API，**不要**再显式 `import ... from 'element-plus'`，
  组件样式由插件按需注入；中文化由 `App.vue` 的 `<el-config-provider :locale>` 统一提供
- 生产部署把 `web/dist` 交给静态服务器，并将 `/api`、`/i/` 反向代理到后端

## 文档与变更记录

- 用户/架构文档：如存在放仓库根或 `V1/docs/`（v2 文档仍在补）
- 每次新增功能、修复问题或行为变更，确保：
  1. 后端测试（`make test`，pytest，写在 `tests/`）通过
  2. 涉及数据结构的变更在 `sapic/migrations/` 注册迁移
  3. 涉及依赖的变更同步更新 `requirements/` 三档文件并 `make install-prod` 复核
- 对外 API 行为（响应字段、错误码、枚举值）不可随意破坏性变更，前端依赖它们

## 持续集成 / 质量

- CI 在 `.github/workflows/ci.yml`：v2 用 `requirements/dev.txt` 安装、跑 `pytest`；
  v1 用 `V1/requirements/dev.txt` 跑遗留 unittest（互不影响）
- 提交前保证：导入可用、应用能启动（`make dev` 或 `make config` 正常）、`make test` 全绿
- 建议同步更新 `ARCH.md` 中的目录/扩展点清单描述

## 已知技术债（改动时注意）

- 存储后端优先级已支持，但**多副本异步复制与对账**尚未实现（仍取第一条成功结果）
- 用户自定义存储后端管理 API、上传票据（Upload Ticket）、相册共享成员管理、OIDC 对接
  仍在待实现列表，相关页面（如 `AdminView`）已留占位提示
- 钩子的插槽/动作目前是「声明即信任」+ 词表清洗，暂无插件市场与签名校验

## 编码前思考
- 明确假设，不确定时询问而非猜测。
- 存在歧义时，列出多种解释，不默默选定单一方案。
- 如果任务有明显更简单的做法，直接指出优化思路。
- 发现代码矛盾、逻辑不一致时及时暂停，请求信息澄清。

## 简洁优先
- 用最少的代码解决问题，拒绝冗余实现。
- 不为一次性需求创建抽象层、复杂架构。
- 不盲目增加扩展性、可配置性，应对“未来可能用到”的场景。
- 若代码可大幅精简，主动重写优化。
- 校验标准：以资深工程师视角判断，代码若过于复杂，立即简化。

## 精准修改
- 仅修改与当前任务直接相关的代码内容。
- 不顺手优化相邻代码、注释、排版格式。
- 不重构原本可以正常运行的代码模块。
- 严格匹配项目现有代码风格，保留原有编码习惯。
- 因本次修改产生的无效导入、废弃变量，可直接删除。
- 发现项目中原有的死代码、冗余内容，仅做文字提醒，不擅自删除。

## 目标驱动执行
- 执行任务前，定义清晰、可落地的成功标准。
- 将“修复Bug”转化为：编写用例复现问题，再调试至用例正常通过。
- 将“新增校验功能”转化为：针对异常输入编写测试用例，保证全部通过。
- 将“代码重构”转化为：完成重构后，确保原有所有测试用例正常运行。
- 多步骤复杂任务，先输出简短执行计划，同时标注每一步的验证方式。
