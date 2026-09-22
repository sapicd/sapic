# sapic 核心架构

> 基于 Flask 的自建图床（picbed），版本 v1.16.7。
>
> 两个最鲜明的特征：**无 ORM、纯 Redis 存储**；**存储后端完全插件化（钩子体系）**。

## 一、技术栈与运行形态

- 语言/框架：Python 3.10+ / Flask（`utils.tool.raise_version()` 启动时强制校验）
- 存储：Redis（唯一必需依赖，建议开启 AOF 持久化）
- 生产部署：gunicorn + gevent，`workers = CPU 核数`，配置文件 `src/sapicd.py`
- 运维入口：`flask sa create | clean | upgrade`（`src/utils/cli.py`）

## 二、目录分层与依赖方向

```
src/
├── app.py        应用入口：Flask 实例、全局钩子、蓝图注册、错误处理
├── config.py     配置：.cfg 文件 → 环境变量 → 默认值
├── sapicd.py     gunicorn 配置
├── views/        路由层  front.py(页面) / api.py(/api/* JSON)
├── libs/         领域核心  storage.py(Redis 单例) / hook.py(插件系统)
├── utils/        基础设施  tool.py(纯工具) / web.py(依赖 Flask 上下文)
│                          / cli.py / _compat.py / exceptions.py / log.py
├── hooks/        内置钩子，一个 .py 即一个插件
├── templates/    static/  tests/
```

依赖方向单向：`views → libs/utils → utils.tool`。
`utils.tool` 不依赖 Web 框架，`utils.web` 才依赖 `request` / `g` / `current_app`。

## 三、配置系统

```python
envs = Properties(join(dirname(__file__), ".cfg"), from_env=True)
```

`Properties` 读取 `src/.cfg`（k=v，所见即所得，不入库）→ 查不到则读同名环境变量 → 最后用默认值。

`GLOBAL` 主要项：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `Host` / `Port` | `0.0.0.0` / `9514` | 监听地址端口 |
| `SecretKey` | 内置串 | Web 应用密钥 |
| `MaxUpload` | `20` | 上传上限，单位 MB |
| `ProxyFix` | 关 | 是否信任代理标头 |
| `HookReloadTime` | `600` | 钩子管理器重载间隔，单位秒 |
| `AllowTags` / `AllowStyles` | 空 | 站点设置额外允许的 HTML 标签属性/样式 |
| `HookPkgStorageDir` | 空 | 第三方扩展包持久化目录 |

`REDIS = sapic_redis_url` 是**唯一必需项**，格式 `redis://[:password]@host:port/db`。

## 四、数据层：两类 Redis 存储

### 1) 系统级键值 — `libs/storage.py: RedisStorage`

线程安全单例，所有内容 JSON 序列化后存放在**同一个 hash** `picbed:dat` 中：

| key | 内容 |
| --- | --- |
| `siteconfig` | 站点设置（上传字段、后缀、匿名开关、`upload_group`/`upload_limit` 等） |
| `hookloadtime` | `{pid: 加载时间戳}`，驱动多进程热重载 |
| `hookthirds` | 第三方钩子模块名列表 |
| `hookstate` | `ENABLED.xxx` / `DISABLED.xxx` |

### 2) 业务数据 — 直接使用 `utils.web.rc`

模块级 Redis 连接，key 统一由 `utils.tool.rsp()` 加 `picbed:` 前缀：

| key | 类型 | 说明 |
| --- | --- | --- |
| `picbed:accounts` | set | 用户名集合 |
| `picbed:account:{usr}` | hash | 用户档案（werkzeug 密码 hash、`is_admin`、`status`、`label`、`ucfg_*` 用户级配置） |
| `picbed:index:global` | set | 全站图片 sha 索引 |
| `picbed:index:user:{usr}` | set | 用户图片 sha 索引 |
| `picbed:image:{sha}` | hash | 图片元数据，支持 `expire` 实现图片过期 |
| `picbed:linktokens` + `picbed:linktoken:{id}` | set + hash | LinkToken 免登录上传凭证 |
| `picbed:report:linktokens:{usr}` | list | 使用报告 |
| `picbed:msg:admin:control` / `picbed:msg:{usr}` | list | 页面闪现消息 |

`picbed:image:{sha}` 字段：`filename` / `upload_path` / `src` / `sender` / `senders` / `album` / `ctime` / `status` / `user` / `is_video` / `method` / `title` / `origin`。

sha 生成规则：`"sha1.%s.%s" % (时间戳, sha1(filename))`。
查询普遍使用 `pipeline` + `hmget` 批量拉取。

## 五、请求生命周期

```python
@app.before_request
def before_request():
    g.rc = rc
    g.site = get_site_config()
    g.cfg = Attribute(g.site)
    g.signin, g.userinfo = default_login_auth()
    #: Trigger hook, you can modify flask.g
    hm.call("before_request")
    g.userinfo = Attribute(change_userinfo(g.userinfo))
    g.is_admin = is_true(g.userinfo.is_admin)
    ...
```

- `app.response_class = JsonResponse` → 视图直接 `return dict` 即输出 JSON
- `after_request`：触发 `after_request` 钩子 → 按站点配置加 CORS → 统一加 `X-Content-Type-Options: nosniff`、`X-Frame-Options: SAMEORIGIN`
- 错误处理：`/api/` 前缀返回 JSON，其余渲染 `public/error.html`；自定义异常 `ApiError` / `PageError`
- `context_processor` 向模板注入 `Version` / `is_true` / `timestamp_to_timestring` / `get_page_msg` / `get_push_msg`

## 六、钩子（插件）体系 — 架构最核心的部分

`libs/hook.py` 中的 `HookManager`：

### 装载

- 扫描 `src/hooks/*.py`（`family=local`）+ Redis 登记的第三方模块名（`family=third`）
- 模块必须带 `__version__` 与 `__author__`
- 第三方额外要求：semver 版本号合法、`__appversion__` 与当前应用版本匹配（`semver.match`）
- 元数据：`__hookname__`（友好名）、`__state__`、`__catalog__`、`__description__`

### 启停与热重载

- 状态写入 Redis（`ENABLED.xxx` / `DISABLED.xxx`），控制台可在线开关
- 按 **pid** 记录加载时间，超过 `HookReloadTime` 或文件 mtime 变化即重新扫描
- gunicorn 的 `on_reload` / `on_exit` 会清理 `hookloadtime`

### 三个调用入口

| 入口 | 用途 | 返回 |
| --- | --- | --- |
| `hm.call(name, _include, _exclude, _mode, _every, ...)` | 调用钩子同名函数 | `[{code, sender, ...}]` |
| `hm.call_intpl(name, **ctx)` | 渲染钩子里的 `intpl_xxx` 模板片段 | `Markup` HTML |
| `hm.proxy(name)` | 取到模块对象直接调方法 | module |

`_mode` 支持 `any_true`（任一成功即中止）、`any_false`（任一失败即中止）；`_every` 可改写每个钩子的执行结果。

### 扩展点清单

| 扩展点 | 类型 | 说明 |
| --- | --- | --- |
| `upimg_save` | func | 图片存储后端 |
| `upimg_delete` | func | 图片删除清理 |
| `upimg_stream_processor` | func | 上传二进制改写（如转 webp），可改 suffix |
| `upimg_stream_interceptor` | func | 上传拦截器，拒绝即中止 |
| `sendmail` | func | 邮件发送，`any_true` 模式 |
| `login_handler` / `logout_handler` | func | 站点级第三方登录 |
| `route` | func | 扩展页面路由，暴露于 `/extendpoint/<hook_name>/<route_name>` |
| `before_request` / `after_request` | func | 全局请求切面 |
| `profile_update` | func | 用户资料更新 |
| `intpl_*` | tpl | 控制台模板片段注入点 |

### 前端集成

- 模板全局注入 `intpl` / `get_call_list` / `emit_assets` / `es`
- 钩子自带的 `templates/` 挂进 Jinja `ChoiceLoader`，`static/` 走 `/assets/<hook_name>/<filename>`

### 内置钩子

| 钩子 | catalog | 说明 |
| --- | --- | --- |
| `up2local` | upload | 保存到 `static/upload/`，默认后端 |
| `up2upyun` / `up2qiniu` | upload | 又拍云 / 七牛云 |
| `up2github` / `up2gitee` | upload | GitHub / Gitee 仓库 |
| `pic2webp` | - | 上传流转 webp |
| `sendmail` | - | SMTP 邮件发送 |
| `token` | - | LinkToken 免登录上传凭证 |

第三方生态（AWS S3、sm.ms、superbed 等）以独立 pip 包形式安装。

## 七、核心流程：上传 `POST /api/upload`

```text
1. 匿名开关 / 用户状态校验
   └─ status -2/-1 待审核、0 禁用 → 禁止上传
2. 适配上传源 → 统一为 {filename, stream, size, mimetype}
   ├─ FormFileStorage    multipart 文件域
   ├─ Base64FileStorage  base64 / Data URI
   └─ ImgUrlFileStorage  远程 URL，服务端下载（可走站点代理）
3. 校验后缀白名单 + 大小限制（upload_size 或 MAX_UPLOAD）
4. upimg_stream_processor   串行改写二进制，可变更 suffix
5. upimg_stream_interceptor any_false，任一拒绝即中止
6. 生成文件名与路径
   ├─ upload_file_rule: time1 / time2 / time3
   ├─ upload_path_rule: date1 / date2
   └─ 用户级 ucfg_* 可覆盖（需 upload_rule_overridden 开启）
7. 选择存储后端
   ├─ upload_includes（默认 up2local，当前版本随机取 1 个）
   ├─ upload_group  按用户 label 分组指定后端
   └─ upload_limit  按用户 label 限制上传数量
8. hm.call("upimg_save") → 全部失败则返回错误
9. Redis pipeline 写入 index:global + index:user:{u} + image:{sha}
   （可选 expire 实现图片过期）
10. 响应 {code, filename, sender, sha, api, tpl:{URL,HTML,Markdown,rST}, src}
11. api_after_handler 统一做 dfr() 中英翻译 + 响应格式转换
```

响应兼容性设计（PicGo / uPic 依赖）：

- `format` 参数控制 src 字段位置，支持点号取值，如 `data.src` → `{..., data: {src}}`
- `status_name` / `ok_code` / `msg_name` 可改写状态码字段名、成功值、消息字段名

删除时对应调用 `upimg_delete` 钩子清理远端文件。

## 八、认证与授权

- **会话**：Cookie `dSid` = urlsafe_b64(`usr.expire.sha256(usr:pwd:expire:SECRET_KEY)`)，每请求由 `default_login_auth()` 校验签名与过期时间
- **四种装饰器**

| 装饰器 | 场景 | 未满足时 |
| --- | --- | --- |
| `login_required` | 页面需登录 | 重定向到 `/login?next=` |
| `anonymous_required` | 页面需匿名 | 重定向到首页 |
| `apilogin_required` | 接口需登录 | 403 |
| `admin_apilogin_required` | 接口需管理员 | 403 / 404 |

- **JWT**（PyJWT）：仅用于邮箱验证、重置密码链接，有效期 10 分钟
- **站点级第三方登录**：控制台 `site_auth` 指定钩子，钩子实现 `login_handler` / `logout_handler`
- **LinkToken**：`hooks/token.py`，免登录受限上传凭证
- 用户状态：`-2/-1` 待审核（仅不能上传）、`0` 禁用、`1` 正常

## 九、前端与运维

- Jinja2 + layui + jQuery
- 模板目录：`public/`（首页、登录、注册、找回密码）、`control/`（`my` 个人中心、`admin` 控制台）、`layout/`、`email/`（独立 Jinja Environment 渲染）
- `static/upload/` 是 `up2local` 的落盘目录
- 控制台支持在线 `pip install` 第三方钩子包（`POST /api/pip/install` → `utils.web._pip_install`），安装到 `HookPkgStorageDir`，该目录在 `app.py` 中被插入 `sys.path`
- 消息机制：管理员消息经 `set_page_msg` / `get_page_msg`，用户消息经 `push_user_msg` / `get_push_msg`

## 十、已知技术债（代码内 TODO 已标注）

- `upimg_save` 当前只取第一条结果，多后端聚合尚未实现
- `POST /api/extendpoint?Object=&Action=` 无鉴权反射调用钩子方法，存在安全风险
- 上传限流用 `scard` 读后判断，并发下存在竞态（首页多线程上传计数错误）
- 无迁移框架，数据结构演进依赖 `flask sa upgrade` 的手写脚本（1.6-1.7 / 1.7-1.8 / 1.16）
- 钩子热重载依赖 Redis 中按 pid 存储的时间戳，多进程场景需 gunicorn 钩子配合清理

## 一句话概括

**Flask 负责 Web 与鉴权，Redis 承担全部持久化，`HookManager` 把上传后端、流处理、邮件、登录、前端片段全部抽象成可热插拔的插件。**
