# sapic (v2) — 项目上下文

sapic 是一个自建图床，**v2 是 API-only 的 Flask 后端 + 独立 Vue 前端**，
**ORM 用 Peewee**（不再是 v1 的纯 Redis 存储），**存储后端与扩展点完全插件化（钩子体系）**。
v1 代码已归档在 `V1/`，仅供对照，不参与 v2 构建；v1 的项目约定见 `V1/AGENTS.md`。
当前版本见 `server/sapic/version.py` 中的 `__version__`。

技术栈（后端）：Python 3.10+，Flask，Peewee，psycopg(binary)，PyMySQL，PyJWT。（v2 不用 Redis。）
前端：`web/` 是独立的 Vue 3 + Vite + Element Plus 应用，与后端通过 `/api` 与 `/raw/` 交互。
详细架构见 `ARCH.md`，部署与运维见 `DEPLOY.md`，贡献流程见 `CONTRIBUTING.md`。

> Python 版本下限是 **3.10**，可自由使用 3.10 语法（`X | Y` 联合类型、match 语句、内置泛型
> `dict[str]` 等）。新增代码统一带类型注解，与既有 `sapic/` 模块风格一致。

## 目录结构

后端在 `server/`，包名 `sapic`，是**纯本地包**（不发布 PyPI、也不做 `pip install`）。
命令均在 `server/` 下执行，`cwd` 已在 `sys.path`，可直接 `import sapic`；依赖由
`server/requirements/` 管理（base/dev/prod/hooks），装在仓库根的 `.venv/`，不要手动 `activate`。

```
.
├── server/               v2 后端（包名 sapic，纯本地包，不发布 PyPI）
│   ├── pyproject.toml    仅 pytest 等本地工具配置（依赖见 requirements/）
│   ├── requirements/     依赖：base.txt（运行时，含内置钩子的 SDK）/ dev.txt / prod.txt
│   ├── .gitignore
│   ├── sapic/            v2 后端包（import sapic）
│   │   ├── __init__.py   create_app() 工厂
│   │   ├── version.py    __version__
│   │   ├── cli.py        flask sa 命令入口（upgrade / create-admin）
│   │   ├── basis/        基础设施层（不依赖业务）
│   │   │   ├── common.py 通用基础函数：as_bool / as_int / is_dev
│   │   │   ├── conf.py   配置类 BaseConfig/DevConfig/ProdConfig + load_config()
│   │   │   ├── db.py     Peewee 数据库连接封装
│   │   │   ├── errors.py ApiError / ErrorCode / 错误处理注册
│   │   │   └── vars.py   常量：BASE_DIR / ENV_PREFIX / LOG_LEVEL_TYPE / 会话与文档地址
│   │   ├── libs/         通用基类、接口类与功能封装（auth/images/albums/storage/users/mail/settings）
│   │   │   ├── auth.py   会话 / PAT / CSRF 与权限装饰器
│   │   │   ├── hook.py   HookManager：清单 / 插槽 / 动作 / 数据集
│   │   │   ├── media.py  文件头解析：宽高探测 + EXIF/XMP 剥离（零依赖）
│   │   │   ├── ui.py     声明式 UI 词表与清洗（唯一可信来源）
│   │   │   ├── user_settings.py 个人偏好键值（默认值 / 校验白名单）
│   │   │   └── userscript.py     油猴脚本源码生成（不嵌令牌）
│   │   ├── utils/
│   │   │   ├── common.py 纯工具函数（不依赖 Flask 上下文，如游标编解码）
│   │   │   └── web.py    Web 工具（依赖 Flask 上下文：响应信封、分页）
│   │   ├── views/        Flask 蓝图与路由（auth/settings/users/backends/uploads/images/albums/plaza/site/health/public/hooks/userscript）
│   │   ├── models/       Peewee 模型（BaseModel）
│   │   ├── migrations/   Peewee 迁移框架（flask sa 命令入口）
│   │   └── hooks/        内置钩子，一个 .py 即一个插件（up2local 等）
│   └── tests/            pytest 测试（test_*.py，pyproject 的 testpaths=["tests"]）
├── web/                  v2 前端（Vue 3 + Vite + Element Plus）
├── V1/                   v1 旧代码与文档，仅存档
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
| 数据库连接封装 | `basis/db.py` |
| 通用基类、接口类、封装功能类 | `libs/`（auth/images/storage/users/mail/settings/hook/ui） |
| 纯工具函数（无 Web 上下文） | `utils/common.py` |
| 依赖 `request` / `g` / `jsonify` 的函数 | `utils/web.py` |
| 视图（蓝图、路由、装饰器与薄封装） | `views/` |

## 常用命令

```bash
make setup            # 安装开发依赖（后端 dev.txt + 前端 pnpm install）
make install-prod     # 生产部署依赖 (server/requirements/prod.txt：base + gunicorn + gevent)
make config           # 打印当前生效配置 (python -c load_config)
make upgrade          # 手动兜底：建表 / 增量迁移（启动时已自动执行）
make create-admin     # 创建管理员，需 U=admin P='密码'
make dev              # 开发服务器 0.0.0.0:9514 (flask run --reload，改代码自动重启)
make serve            # gunicorn 前台运行 (WORKERS=4 -k gevent)
make test             # 后端 pytest
make web-dev          # 前端开发服务器 127.0.0.1:5173（/api 与 /raw/ 代理到 9514）
make web-build        # 前端构建到 web/dist
make clean            # 清理缓存与构建产物
```

变量可覆盖：`make dev PORT=8080`、`make serve WORKERS=8`。`make` 无参数即打印帮助。

`make dev` 自带 `sapic_env=dev`；生产模式（`make serve` 等）必须配置 `sapic_secretkey`
（`server/.cfg` 或环境变量），否则 `load_config()` 直接报错——内置默认密钥是公开字符串。

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
2. 第三方库（`flask`, `peewee`, `pillow`...）
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
- DB / 第三方 SDK 调用需捕获特定异常并转换为 `ApiError` 或带 `message` 的失败响应
- 不用 `print()` 打日志，统一用 `logging.getLogger(__name__)`

### API 响应信封 ★

所有 `/api/v2/*` 响应统一由 `sapic/utils/web.py` 的 `ok()` 包裹（错误走 `ApiError`）：

```json
{ "code": "OK", "message": "", "data": { ... } }      // 成功
{ "code": "NOT_FOUND", "message": "xxx", "data": null } // 失败，code 为 ErrorCode 字符串
```

- 业务成功永远 `code: "OK"`；失败 `code` 是 `ErrorCode` 枚举名（如 `UNAUTHORIZED` /
  `FORBIDDEN` / `NOT_FOUND` / `INVALID_ARGUMENT` 等），**不要自己造字符串**
- 业务消息用英文原文；前端负责本地化，不要在后端返回中文 `message`
- 错误由 `@app.errorhandler(HTTPException)` 统一转成上述信封，视图里直接 `abort(404)` 即可

## 数据库（Peewee）

- 模型集中在 `sapic/models/`，基类 `BaseModel` 已含 `id` / 时间戳等公共字段
- 连接由 `sapic/basis/db.py` 的 `db` 单例管理，配置来自 `load_config()` 的 `DATABASE_URL`
- **结构变更走迁移**：在 `sapic/migrations/` 的 `MIGRATIONS` 注册迁移函数（必须幂等），
  应用启动时由 `auto_upgrade()` 自动执行，`make upgrade` 只作手动兜底；不要直接
  `db.create_tables()` 改线上结构
- 批量操作优先 `atomic()` 事务；查询用 Peewee 表达式，杜绝字符串拼接
- 测试用临时 SQLite（`sapic_db_url=sqlite:///...`），不要依赖具体数据库方言

## v1 兼容与数据迁移 ★

**v1 的 `POST /api/upload` 兼容端点已移除**（原 `views/legacy.py` 已删除）：客户端统一走
`/api/v2/upload`（`views/uploads.py`，字段 `file` 或 `url`，v2 信封），PicGo / uPic / Typora /
ShareX 等的逐项配置见 `docs/usage.md`。**不要再为老客户端补第二套业务实现或 v1 信封。**

- **鉴权**统一用 PAT：`Authorization: Bearer <PAT>`，scope 至少含 `upload`。浏览器会话必须带
  CSRF 头，客户端带不了，所以客户端一律配令牌；全局 CSRF 中间件没有任何端点例外。
- **上传策略**（后缀白名单、图片/视频大小、匿名开关）统一在 `libs/images.py`
  的 `check_upload_limits` / `anonymous_upload_allowed`，上传视图直接复用，不要各写一套。
- **迁移脚本** `tools/migrate_v1_to_v2.py`：读 v1 Redis（`picbed:accounts` / `account:<u>` /
  `index:global` / `image:<sha>` + TTL），写 `users`/`albums`/`images`/`image_backends`。必须保持
  幂等（用户按 username、相册按 `(owner,name)`、图片按 sha 去重）、支持 `--dry-run`、保留 v1 sha
  （`/raw/<sha>` 是已发布的链接）、文件走 `save_object` 重传而不是搬目录；v1 的 `src` 已在主后端
  公开域名下时改为**原地采纳**（`src_object_key` + `--v1-src-prefix`，登记 `ok` 副本、不重传，
  删除仍会删 bucket 对象），只有字节真的没了才登记 `source_url` 外链。改表结构时同步检查这个脚本的字段映射。

## 站点设置

- 默认值集中在 `sapic/libs/settings.py` 的 `DEFAULTS`，读写统一走 `get_setting` / `set_setting`
- `upload_count_limit` 是**单次批次**限制，只由前端上传控件强制；后端每次请求只有一个文件，不做（也无从做）该校验。要服务端配额应另立「每日/每小时次数」这类语义
- 后台通过 `GET/PUT /api/v2/settings` 管理（仅管理员），可写键白名单与类型校验在 `views/settings.py`
- 前台展示字段由公开接口 `GET /api/v2/site` 输出，前端在 `stores/site.js` 消费
- 上传类设置（后缀白名单 / 大小 / 数量 / 视频）在 `views/uploads.py` 生效，注册类设置在 `views/auth.py` 生效；
  新增配置项必须同时接入「后台表单 + 实际生效点」，不要留下只存不用的配置
- 单文件大小上限**按媒体类型分开**：`upload_image_max_size`（默认 10M）与 `upload_video_max_size`（默认 20M），
  由 `views/uploads.py` 的 `_size_limit_mb()` 按后缀选择；URL 抓取时类型未知，先按两者较大值截断，拿到文件名后再按类型校验。
  进程级 `MAX_UPLOAD`（`sapic_maxupload`，默认 25M）映射 `MAX_CONTENT_LENGTH`，是整个请求的硬门槛，
  必须大于站点里最大的单文件上限（multipart 有开销），三者取最小值才是实际上限
- 对外请求代理是 `upload_fetch_proxy`（单个 `http(s)://[user:pass@]host:port`，空 = 只用直连），
  只在 `libs/images.open_remote` 生效：用户 URL **先直连、抓不到才用代理兜底**（DNS 解析失败也算
  「抓不到」，见 `_host_visibility` 的 `None`）；`allow_private=True`（存储后端读取 URL）永远直连。
  格式校验统一走 `utils/common.parse_proxy_url`（写入时 400，运行期记日志并按直连处理）。
  走代理时本地 DNS 不可信（外网域名常解析失败/被污染），SSRF 校验降级为「只拦私有 IP 字面量」，
  这条取舍写在 `_is_public_literal` 的注释里，别把它改成完整 DNS 校验，否则代理就等于没用。
- `password_login`（默认开）关闭后 `views/auth.py` 的登录与注册接口直接 403，登录页只渲染统一登录入口
- 统一登录（OIDC）：`passport` 钩子提供 provider 能力，`views/auth.py` 负责发起/回调与绑定，
  `libs/users.py` 的 `resolve_oidc_user` 处理「已绑定 → 登录 / 双方邮箱均已验证 → 自动关联 / 否则按
  provider 信息建号」（新用户主要入口）；解绑需校验当前密码，避免 OIDC 专用账号锁死自己
- 邮箱验证：注册自动寄令牌，`POST /api/v2/auth/email/verify` 重发、`POST /api/v2/auth/email/confirm`
  提交令牌后置 `email_verified=True`；改邮箱会重置为未验证，且 `resolve_oidc_user` 要求本地已验证
- 后台是**一个入口 + 一个壳**：顶部导航只有「后台管理」，进入后由 `layout/AdminLayout.vue`
  的侧栏在 `/admin/setting` 站点设置（`AdminView`）、`/admin/hooks` 钩子管理（`HooksView`）、
  `/admin/backends` 存储后端（`BackendsView`）、`/admin/users` 用户管理（`UsersView`）之间切换，
  各自挂 `admin.*` 插槽；不要把侧栏再拆成多个顶部导航入口，也不要把这些页面合并回一页；
  新增后台页面时挂到 `/admin` 父路由下并在 `AdminLayout` 的侧栏里登记
- 后台路由对**未登录与普通用户一律返回 404**（`router/index.js` 的守卫把 `requiresAdmin` 的导航
  改写成 `not-found`，保持 URL 不变、不跳登录页、不提示无权限），避免把后台入口的存在与地址暴露出去；
  真正的权限仍由后端 `admin_required` 把关。`/admin`（默认子路由）与 `/admin/setting` 都直接渲染站点设置，
  不要恢复成重定向——重定向会让未授权访问的地址栏发生变化
- 版本更新检测只在后台：`GET /api/v2/settings/version`（admin，`libs/release.py`，24h 进程内缓存、
  失败降级为 `error` 不抛错），`AdminLayout` 侧栏底部显示当前版本与「可更新」标签，点开看详情与发布页；
  `sapic_updatecheckurl` 置空即关闭（内网部署不允许出网时）。版本比较在 `utils/common.is_newer_version`，
  只做「数字段 + 同号正式版优先」的 semver 子集，不引入额外依赖
- 用户管理走 `GET/PATCH/DELETE /api/v2/users`（仅管理员，`views/users.py`）：列表支持关键词与状态筛选
  （`-2` 已拒绝 / `-1` 待审核 / `0` 已禁用 / `1` 正常），分页用 `page` / `page_size`（默认每页 15，
  `paginate_page` + `total`，后台可跳页；不带 `page` 仍是游标模式），PATCH 可改 `status` 与 `is_admin`；
  禁用/拒绝会自增 `session_version` 让既有会话失效，且管理员不能改自己的状态或撤销自己的管理员权限、
  也不能删除自己。DELETE 走 `libs/users.purge_user`：**硬删除**（用户名与图片 sha 要能被重新占用），
  连带删除其相册、图片与副本（副本先调 `upimg_delete` 清文件）、PAT、上传票据、用户设置与个人存储后端；
  别人上传到其相册的图片会移回上传者自己的默认相册
- 注册审核：`register_review` 开时新账号是 `-1`，PATCH `{status: -2, reason}` 记录拒绝理由到
  `users.status_reason`（迁移 v010，换成其他状态自动清空）。只有「待审核 → 通过/拒绝」这一跳才发
  审核结果邮件（`libs/users.notify_review`，仅发给已验证邮箱，失败只记日志）；启用/禁用不算审核动作，
  别顺手发邮件
- **自助注销**（`DELETE /api/v2/auth/account`，`libs/users.self_delete`）：必须提交当前密码，
  名下有未删除图片直接 409 并告知数量（不能让 `purge_user` 悄悄删掉图），管理员不能自删
  （避免后台失去入口，由其他管理员在 `DELETE /users` 处理）。成功后 `logout_user()` 清会话，
  前端「账号信息」页底部的危险操作区负责二次确认；不要把注销做成不带密码的 GET/一键按钮
- **只有 `status=1`（正常）的账号能登录、持有会话或使用 PAT**（`libs/users.authenticate` /
  `libs/auth._load_current_user` / `resolve_pat` 同一口径）：待审核与已拒绝都按未激活处理，
  OIDC 建号走审核时也不发会话（重定向 `/login?oidc=inactive`）
- PAT 的 `scopes` 是**真实生效**的（`libs/auth.py`）：`read` 覆盖安全方法、`upload` 覆盖上传、
  `write` 覆盖其余改动、`admin` 覆盖管理接口；缺省 `read/upload/write`，`admin` 仅管理员可申请。
  `login_required` 按请求方法自动校验，`admin_required` 额外要求 `admin`，上传接口支持匿名所以在
  视图里显式 `require_scope(SCOPE_UPLOAD)`。新增接口只要走这两个装饰器就自动受限，**不要自己写
  鉴权分支**；Cookie 会话不受 scope 约束（等价账号本身）

## 相册与可见性 ★

权限以**相册**为维度：每张图片都必须属于一个相册，可见性由相册决定，单张图片可覆盖。

- 上传兜底：`libs/albums.resolve_album(owner)` —— 登录用户落到其**默认相册**
  （`albums.is_default`，新用户注册时创建，可见性取设置 `default_album_visibility`，默认 `public`），
  匿名上传落到**系统相册**（`albums.owner_id` 为 NULL 的「公共相册」）。`create_image()` 内部兜底，
  不要绕过它直接建 `Image`，否则会出现无相册（= 默认可公开）的图片。
- 单图覆盖：`Image.visibility` 为 NULL 表示跟随相册；前端详情页用「跟随相册」选项清空。
- 图片不能被摘出相册：`PATCH /api/v2/images/<sha>` 传空 `album_id` 直接 400，否则
  `effective_visibility()` 会把「无相册 + 无覆盖」当成 public，私有图就泄漏成匿名可读。
- 默认相册不可删除（409）；系统相册（`owner_id` 为 NULL 的「公共相册」）对普通用户不可见，
  管理员在 `GET /api/v2/albums` 会额外拿到 `role=system` 的那条，用于筛选匿名图片。系统相册
  无 owner，`PATCH/DELETE /albums/<id>` 对所有账号都是 404，所以它始终保持 `public`，
  匿名图片因此在管理员的 `scope=all` 全站视图里正常出现（普通用户的图库不会包含它们）。
  匿名图的 `owner_id` 为 NULL，既不匹配「我的图」也不在任何共享里，所以 `GET /images?album_id=<系统相册>`
  在 `views/images.py` 里对管理员**自动放大到全站口径**（相册页点进来只带 album_id，不放大就永远是空列表）；
  该特例只对 `owner_id is NULL` 的相册生效，别人的公开相册仍不出现在个人图库里。
- 共享授权（`album_shares`）按用户名添加：`POST /albums/<id>/shares` 添加（可传 `expires_in` 秒）、
  `PATCH .../shares/<uid>` 调整权限或有效期、`DELETE .../shares/<uid>` 移除；只有所有者能管理，
  私有相册添加成员后自动提升为 `shared`。过期授权等于不存在——鉴权统一走
  `libs.albums.share_for()`（`can_view` / `can_write` / 相册与图片列表都过它），别直接查 `AlbumShare`。
  未激活（非 `status=1`）的账号不能被添加为成员，且接口不区分「不存在」与「未激活」。
  `permission=read` 只能浏览，`write` 额外允许把图片上传进该相册（`libs.albums.can_write`，
  在 `views/uploads.py` 生效；仍不能修改/删除别人的图片）。`GET /albums` 对共享相册返回
  `permission` 字段，前端据此过滤上传目标。
- 结构变更走 `sapic/migrations/`：`v002_album_ownership` 负责 `owner_id` 可空、`is_default` 列
  与存量图片回填，必须保持幂等。
- 图片列表（`GET /api/v2/images`，`libs.images.visible_query`）是**个人图库**：只返回自己的图片 +
  共享给自己的相册，**不包含他人的公开图片**（否则等于绕过了广场的显式发布）；接口要求登录，匿名 401。
  公开图仍可按 `src` / `/raw/<sha>` 访问，那是图床的外链语义，与列表无关。
  **管理员默认同样是个人图库**，全站图片必须显式传 `scope=all`（非管理员 403，非法值 400，
  前端「图片」页有「显示全站图片」按钮）：管理视图是主动点击而不是页面默认状态。全站视图
  **只列公开图片**（`public_condition`），私有与共享相册里的图不会因为管理员身份出现在列表里，
  要看别人的私有图只能靠相册授权或单图直链。
- 图片广场（`GET /api/v2/plaza`，匿名可读）是**曝光渠道而非权限**，且**默认关闭**：个人自建图床用
  不到公开曝光，开启 `plaza_enabled` 才生效（专业版/社区部署按需打开，开启即意味着承担 UGC 审核与
  投诉成本）。
  只有有效可见性为 `public` 的图片会进列表，且必须显式发布（`albums.plaza` 相册开关 +
  `images.plaza` 单图三态，`NULL` 跟随相册）；迁移 `v005` 加列，存量默认不发布。
  站点设置 `plaza_enabled` 关掉后，后端 `GET /plaza` 直接 404，前端同时隐藏一切广场入口
  （导航项、相册列表/编辑里的发布开关、图片详情里的广场行与单图设置），`/plaza` 路由回退首页。
- **个人 RSS 已整体移除，不要恢复**（v1 的 `/feed`）：匿名聚合出口会把「某用户有哪些图、何时上传」
  整份暴露给任何抓取方，而它带来的只是低频的站外订阅。已删除 `views/feed.py`、`libs/feed.py`、
  `libs.images.feed_query`、站点设置 `rss_enabled` 与用户设置 `rss_enabled`；MIGRATION #26 标 ⛔。
  需要分享就发单图直链，不要再造「公开列表类」的匿名出口。
- 油猴脚本（`GET /api/v2/userscript.user.js`，`libs/userscript.build_userscript`）按用户生成，
  挂在 API 前缀下（反代只需 `/api/` 一条规则；v1 的 `/sapic.user.js` 根路径已移除，脚本
  `@updateURL` 指向新地址）：
  受个人设置 `userscript_enabled`（默认关）控制，关掉即 404。**源码里绝不嵌令牌**——v1 把 LinkToken
  写进脚本的做法已废弃；脚本首次上传时让用户粘贴只含 `upload` scope 的 PAT，存在油猴存储里。
  上传走 `POST /upload` 的 `url` 字段（服务端抓取，GM_xmlhttpRequest 免 CORS），不要改成浏览器直传二进制。
  该端点刻意不用 `login_required`：GET 会要求 `read`，而安装地址只应需要 `upload`。
- 个人偏好（油猴开关、个人背景）走 `GET/PUT /api/v2/auth/settings`，落在 `user_settings` 键值表，
  键、默认值与校验集中在 `libs/user_settings.py` 的 `DEFAULTS`（未知键直接 400，不要绕过它写库）。
  个人背景优先于站点背景；`bg_opacity` 为 `null` 表示跟随站点。新增偏好必须同时接进设置页与生效点。
- 分享模板（`tpl`）：`libs.images.share_templates` 生成 `URL` / `HTML` / `Markdown` / `rST` 四项，
  键名与 v1 的 `gen_url_tpl` 保持一致（视频的 Markdown/rST 用 `<figure><iframe>`），
  由 `serialize_image` 随图片一起返回；详情页「复制与分享」直接消费，不要再在前端手拼模板。
- 图片地址（`src`）：公开图直接返回优先级最高副本的直链（钩子 `upimg_save` 返回的 `src`），
  私有图固定走 `/raw/<sha>` 由 sapic 鉴权后输出；私有远程副本在 `/raw/` 内流式转发，不做 302，
  避免暴露源站地址。没有直链的后端（未配 `domain` 的本地存储）同样回落到 `/raw/<sha>`。
- 缩略图（`thumb`）：只有列表与广场（共用 `libs.images.album_serializer`）会输出，值为
  `src` + 存储后端 `config.thumb_suffix`（七牛 `?imageView2/2/w/400`、又拍 `!/fw/400`，裸查询串
  自动补 `?`，`libs/storage.thumb_suffix`）。仅当 `src` 本身是公开直链（非 `/raw/<sha>`、非外链源站）
  且图片不是视频时才有值——`src` 与 `tpl` 永远是原图，**不要把后缀拼进 `src`**，否则分享出去的
  直链会被永久缩小。配置项在驱动 `config_schema` 里声明（`up2qiniu` / `up2upyun` 已有），
  本地存储、GitHub/Gitee 没有图片处理能力，不要给它们加这个字段。
- 外链登记（`images.source_url`，`POST /images/import`）不下载文件、不写副本：公开图 `src` 直接是源站地址，
  私有图经 `/raw/<sha>` 转发；删除只删元数据。批量操作走 `POST /images/batch/delete` 与
  `PATCH /images/batch`（≤100 张，只允许自己的图片，移动目标需 `can_write`）。
- 图片有效期（`images.expire_at`，`NULL` = 永久）：上传传 `expire`（秒，v1 同语义），
  `PATCH /images/<sha>` 传 `expire_at`（绝对时间戳，`null` 取消）。**到期即视为不存在**——
  `/raw`、详情、列表、广场、相册计数统一走 `models.image.live_condition()`（`status=enabled`
  且未过期），不要只判断 `status`。清理任务 `libs.images.purge_expired` 硬删除副本与记录
  （过期不是软删），由 `before_request` 节流兜底（每进程 5 分钟、单批 200 张）+ 运维命令
  `flask sa purge-expired`。站点设置 `image_expire_default_days`（未指定时的默认寿命）与
  `image_expire_max_days`（上限，`0` 不限制）均为 0 时表示永久；上限生效后不再允许永久图片。
- 存储 key 固定为 `{用户}/{年}/{月}/{日}/{ASCII 文件名}-{sha 片段}.{ext}`（`libs.images.upload_path_for` +
  `create_image`），后缀保证同名文件不被覆盖；文件名经 `secure_filename` 清洗，主体被整段清空时用
  `{yyyyMMddHHmmss}{6 位随机}` 兜底（不同中文名不会撞成同一个 `image`），删除按 `object_key` 执行。
- 媒体元数据由 `libs/media.py` 处理，**零依赖**（只读文件头，不引 Pillow；Pillow 只服务于 `pic2webp` 钩子）：
  `create_image` 在 `process_stream` 之前调 `strip_metadata()`（JPEG 去 APP1 的 EXIF/XMP、PNG 去 `eXIf`
  与 XMP 文本块、WebP 去 `EXIF`/`XMP ` 块并修 RIFF 长度与 VP8X 标志），落盘字节不留拍摄时间/相机/GPS；
  之后对处理过的字节调 `image_size()` 写入 `images.width/height`（外链登记与不可解析载荷为 `NULL`）。
  两个函数失败都只返回 `None` / 原字节，**任何解析异常都不允许中断上传**。

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
  「加速域名」`domain` 时附带 `src` 直链；没有 `src` 时服务层回落到 `/raw/<sha>`）与
  `upimg_delete(sha, upload_path, filename, basedir, save_result)`（失败不外抛）

### 声明式 UI 契约

`sapic/libs/hook.py` 的 `HookManager` 通过以下约定聚合每个钩子的 UI：

| 钩子函数 | 返回值 | 说明 |
| --- | --- | --- |
| `hook_manifest()` | dict | `{title, catalog, config_schema, actions, data_sources, slots}` |
| `slot_<name>(context=None, values=None)` | list[节点] | 渲染某个插槽的节点树 |
| `action_<name>(payload=None, context=None, values=None)` | dict | `{code, message, toast, refresh}` |
| `data_<name>(query=None, context=None)` | dict | `{items: [...], total: int}` |

- 存储驱动（`catalog=upload`）的 `config_schema` 字段由**存储后端**消费，不在「钩子配置」里出现：
  后端行新增/修改时按 `required` 校验、缺项标「待配置」，`driver_backend()` 仍兼容钩子级默认值
- `config_schema` / `actions` / `data_sources` / `slots` 全部经 `sapic/libs/ui.py` 的
  `clean_*` 清洗：未知类型/键被丢弃、`href` 仅允许 `http(s)` 与站内 `/`、
  `action` 必须声明于 manifest，否则被静默忽略（防 XSS / 越权）
- `slots` 的 `name` 必须在 `ui.SLOTS` 白名单内；`admin.*` 开头的插槽仅管理员可见
- `actions` 里声明 `scope: "admin"` 的动作（如各存储后端的 `ping`）只允许管理员调用，
  `POST /hooks/<name>/actions/<action>` 会校验；`GET /hooks/<name>/data/<source>` 数据集接口
  同样仅管理员。新增动作时若会碰服务器路径或第三方凭据，必须标 `scope: "admin"`
- 节点类型完整列表见 `ui.py`：`fieldset/group/row/col/tabs/collapse/list/list_item`、
  `text/alert/badge/image/code/divider`、`input/number/password/textarea/switch/select/radio`、
  `button/link/dropdown/dropdown_item`
- `action` 返回里的 `toast` 仅当 `level` 在白名单内才会透传给前端；`refresh=True` 触发前端刷新
- 钩子自带的私有依赖：在 `server/requirements/` 下加文件并用 `try/except ImportError` 兜底英文提示，
  **不要**在 `server/requirements/base.txt` 强制引入可选 SDK

### 第三方钩子包与市场 ★

`libs/hook_pkg.py` 负责装包，`views/hooks.py` 只做路由与权限，端点全部 `admin_required`：

| 端点 | 作用 |
| --- | --- |
| `GET /hooks/market` | 拉官方 `list.json`（`sapic_hookmarketurl` 可换镜像），6 小时缓存，合并本地 `installed` / `loaded`；只展示 `appversion` 主版本 ≥ 2 的条目（V1 契约不兼容，已加载的例外） |
| `POST /hooks/install` | `pip install --target <HOOK_PKG_STORAGE_DIR>`；包名与 `index_url` 先校验，180s 超时 |
| `GET /hooks/packages` | 目标目录里的 `*.dist-info` 清单（不跑 `pip list`，避免子进程开销） |
| `POST /hooks/import` | 把模块名写入 `hooks_imported`，非法钩子会回滚 |
| `DELETE /hooks/import/<module>?purge=1` | 顺带删除包文件；只删目标目录内、防 `../` 穿越 |

- `HOOK_PKG_STORAGE_DIR` 默认 `data/hooks`，**只做 `sys.path` 条目、不做扫描目录**（append 不 insert）：
  `pip install --target` 会连带装依赖，逐个 `exec` 这些文件等于执行无关第三方代码，第三方钩子统一走
  `hooks_imported` 的模块名。`init_app` 负责建目录，置空即关闭后台安装能力（`package_dir()` 返回 `None`）。
- 装包等于在服务端执行代码：目标目录永远来自配置而非请求，pip 用列表参数（无 shell），
  新增入口不要引入「客户端指定路径 / 解压上传 zip」这类能力。
- 重装包后必须让 `sys.modules` 缓存失效，`HookManager._load_imported` 已做 `invalidate_caches()` +
  `pop()`，不要绕过它直接 `importlib.import_module`。
- 多 worker 部署下 `ensure_fresh`（1s 节流）会比对 `hooks_state` / `hooks_imported` 并把已登记模块的
  源文件 mtime 计入签名，安装/启停/升级才会传播到其他进程；改这块逻辑时别退回「只看内置目录签名」。

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
- **图标用字符串名引用时必须全局注册**：菜单 / 侧栏 / 设置分栏等通过 `icon: 'Brush'` +
  `<component :is="icon" />` 使用图标，模板里不会报错但图标静默不渲染，必须在 `web/src/main.js`
  的 `GLOBAL_ICONS` 里补上（同时补对应的具名 import）。新增/改动菜单项时要顺手核对一遍
- **界面固定中文，不做多语言**：不要在模板里引入 `vue-i18n` / `t()`，用户可见文案直接写中文；
  Element Plus 自带文案由 `App.vue` 的 `<el-config-provider :locale="zhCn">` 统一提供
  （`html lang` 在 `index.html` 里固定 `zh-CN`）
- **接口错误文案**：后端 `message` 固定英文原文，界面中文由 `web/src/api/messages.js` 的
  `localizeMessage(message, code)` 转换（精确词典 → `%` 模板规则 → `ErrorCode` 兜底），
  展示统一走 `api/client.js` 的 `errorMessage(error, fallback)`，不要直接 `ElMessage.error(error.message)`。
  新增/修改后端 `ApiError` 文案时同步这个词典，否则只能退化到按 `code` 的中文兜底
- Element Plus 按需引入（`unplugin-auto-import` + `unplugin-vue-components`）：模板直接写 `<el-xxx>`，
  脚本直接用 `ElMessage` / `ElMessageBox` 等 API，**不要**再显式 `import ... from 'element-plus'`，
  组件样式由插件按需注入；中文化由 `App.vue` 的 `<el-config-provider :locale>` 统一提供
- 视频按 `images.is_video` 切换渲染：详情页用原生 `<video controls playsinline>`（限制 `max-height`），
  图片列表 / 广场 / 上传结果用 `<video muted preload="metadata">` 取首帧当封面（`pointer-events: none`
  让点击落到卡片上）。不要拿 `el-image` 渲染视频，那只会显示裂图
- 生产部署把 `web/dist` 交给静态服务器，并将 `/api`、`/raw/` 反向代理到后端

## 文档与变更记录

- 用户/架构文档：如存在放仓库根或 `V1/docs/`（v2 文档仍在补）
- 每次新增功能、修复问题或行为变更，确保：
  1. 后端测试（`make test`，pytest，写在 `tests/`）通过
  2. 涉及数据结构的变更在 `sapic/migrations/` 注册迁移
  3. 涉及依赖的变更同步更新 `server/requirements/` 三档文件并 `make install-prod` 复核
- 对外 API 行为（响应字段、错误码、枚举值）不可随意破坏性变更，前端依赖它们

## 持续集成 / 质量

- CI 在 `.github/workflows/ci.yml`：v2 用 `server/requirements/dev.txt` 安装、跑 `pytest`；
  v1 用 `V1/requirements/dev.txt` 跑遗留 unittest（互不影响）
- 提交前保证：导入可用、应用能启动（`make dev` 或 `make config` 正常）、`make test` 全绿
- 建议同步更新 `ARCH.md` 中的目录/扩展点清单描述

## 已知技术债（改动时注意）

- 存储后端已可管理（`/api/v2/backends` + `/admin/backends`）：上传同步写 `priority` 最小的启用后端，
  其余启用的后端由后台线程池异步补副本（站点设置 `storage_replica`，默认开；失败只记在副本行上，
  不影响上传）。**副本对账/自动补建**（新增后端后回填历史图片、CRC 校验）仍未实现
- 用户自定义存储（`storage_backends.scope="user"` + `owner`）的**数据与解析层已就绪**
  （`list_backends()` 按归属过滤、`UserBackend.priority` 覆盖、站点开关 `allow_user_backends`），
  但用户端 CRUD API/UI 未实现；管理员后台只管理 `scope="system"` 的行。上传票据（Upload Ticket）
  仍在待实现列表
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
