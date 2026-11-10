# API 参考

## 约定

- 业务接口前缀 `/api/v2`，请求与响应都是 JSON（上传除外，走 `multipart/form-data`）。
- 根路径上只有一个不属于 `/api/v2` 的端点：`GET /raw/<sha>`（图片输出，已发布的直链由它兜底）。
  油猴脚本在 `/api/v2/userscript.user.js`。
- **成功**：

```json
{ "code": "OK", "message": "", "data": { } }
```

- **失败**：

```json
{ "code": "NOT_FOUND", "message": "image not found", "request_id": "9f2c..." }
```

`code` 取自 `sapic/basis/errors.py` 的 `ErrorCode`：
`BAD_REQUEST` / `PARAM_ERROR` / `UNAUTHORIZED` / `FORBIDDEN` / `NOT_FOUND` /
`METHOD_NOT_ALLOWED` / `CONFLICT` / `PAYLOAD_TOO_LARGE` / `RATE_LIMITED` /
`INTERNAL_ERROR` / `SERVICE_UNAVAILABLE`。

`message` 固定英文，由前端 `web/src/api/messages.js` 映射成中文展示；
排查问题时可把响应头 / 响应体里的 `request_id` 与服务端日志对上。

```{note}
这是**传输层**信封。钩子动作、数据集等内部返回值会原样放进 `data`，里面可能再有
`code` / `message` 字段——那是业务层结果，与这里的 `code` 不是一回事，
详见[钩子基础契约](extend/contract.md)。
```

## 鉴权

两种方式，任选其一：

1. **会话 Cookie**（浏览器）：先 `GET /api/v2/auth/csrf` 拿 CSRF 令牌，
   写操作（POST/PUT/PATCH/DELETE）带 `X-CSRF-Token` 请求头。登录成功后
   `POST /auth/login` 的响应里也会返回最新令牌。
2. **个人访问令牌（PAT）**：`Authorization: Bearer sp_xxxxxxxx`。令牌有四档 scope：
   `read`（安全方法）、`upload`（上传）、`write`（其它改动）、`admin`（管理接口），
   缺省 `read` / `upload` / `write`；`admin` 只有管理员能申请。

客户端（PicGo / uPic / Typora 等）一律用 PAT，配置方式见[快捷上传](usage.md)。

只有 `status=1`（正常）的账号能登录、持有会话或使用 PAT；待审核、已拒绝、禁用一律无效。

## 分页

列表接口默认为游标分页：

```text
GET /api/v2/images?limit=20&cursor=<上一页返回的 next_cursor>
```

```json
{ "items": [], "next_cursor": "…", "has_more": true, "limit": 20 }
```

`limit` 上限 100；翻页只用 `next_cursor`，不要自己算 offset。

图片列表（`GET /api/v2/images`）额外支持页码模式，给带页码器的界面用：传 `page` 即切换
（`page_size` 默认 15、上限 100），响应多一个 `total`：

```text
GET /api/v2/images?page=2&page_size=15
```

```json
{ "items": [], "total": 57, "page": 2, "page_size": 15, "has_more": true }
```

两种模式排序一致（`created_at` 倒序、`id` 兜底），不带 `page` 时行为保持不变。
后台接口（如 `GET /users`）只提供页码模式，默认每页 15，前端用页码器直接跳页。

列表默认只含自己的图片与共享给自己的相册。**管理员也不例外**：要看全站图片必须显式传
`scope=all`（前端「图片」页有对应按钮），非管理员传该参数返回 403，非法值返回 400。
`scope=all` 只放大到**公开图片**：别人的私有相册、共享相册里的图不会出现在这个视图。

## 主要端点

### 账号与认证

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/auth/csrf` | 取 CSRF 令牌 |
| GET | `/auth/session` | 当前会话（含用户与是否管理员） |
| POST | `/auth/register` / `/auth/login` / `/auth/logout` | 注册 / 登录 / 登出 |
| POST | `/auth/password/forgot` / `/auth/password/reset` | 找回密码（需已验证邮箱） |
| PUT | `/auth/password` | 修改密码（吊销既有会话） |
| POST | `/auth/email/verify` / `/auth/email/confirm` | 发验证邮件 / 提交令牌 |
| PUT | `/auth/profile` / `POST /auth/avatar` | 资料、头像（服务端裁剪写入） |
| DELETE | `/auth/account` | 自助注销（需密码，名下有图片则 409） |
| GET | `/auth/identities` | 可用的登录 Provider 与绑定状态 |
| DELETE | `/auth/identities/<name>` | 解绑（需密码） |
| GET/PUT | `/auth/settings` | 个人偏好（油猴开关、个人背景等） |
| GET/POST/DELETE | `/auth/tokens`、`/auth/tokens/<id>` | PAT 管理 |
| GET | `/auth/oidc/<name>`、`/auth/oidc/<name>/callback` | 第三方登录（见 [登录 Provider](extend/provider.md)） |

### 图片

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/upload` | 上传：`file` 或 `url`，可选 `album_id` / `title` / `expire`（秒）；`url` 由服务端抓取，直连失败可按站点设置 `upload_fetch_proxy` 走代理 |
| GET | `/images` | 个人图库：`album_id` / `keyword` / `tag` 筛选，游标或 `page` / `page_size` 分页；管理员可传 `scope=all` 看全站公开图，按系统相册（`is_system`）筛选时自动放大到全站口径 |
| GET | `/images/<sha>` | 详情（含副本信息、`can_edit`、分享模板 `tpl`） |
| PATCH | `/images/<sha>` | 改 `title` / `album_id` / `visibility` / `tags` / `plaza` / `expire_at` |
| DELETE | `/images/<sha>` | 删除（属主或管理员，逐副本删文件） |
| POST | `/images/import` | 外链登记（不下载、不写副本） |
| POST | `/images/batch/delete`、`PATCH /images/batch` | 批量删除 / 批量改属性（≤100 张） |
| GET | `/plaza` | 图片广场（匿名可读，`plaza_enabled` 关闭时 404） |

上传成功返回 `201` 与 `{"image": {…}}`，图片对象主要字段：

`sha`、`filename`、`title`、`size`、`mime`、`is_video`、`width`、`height`、
`visibility`、`plaza` / `plaza_effective`、`tags`、`album_id`、`album`、
`created_at`、`expire_at`、`external`、`src`、`tpl`（URL / HTML / Markdown / rST 模板）。

`src` 已按可见性处理：公开图给直链（没有配 `domain` 的存储回落到 `/raw/<sha>`），
私有图固定 `/raw/<sha>`。

### 相册

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/albums` | 列表（管理员额外拿到 `role=system` 的系统相册）/ 新建 |
| PATCH/DELETE | `/albums/<id>` | 改名、描述、封面、可见性 / 删除（默认相册 409） |
| GET/POST | `/albums/<id>/shares` | 共享成员列表 / 添加（可带 `expires_in`） |
| PATCH/DELETE | `/albums/<id>/shares/<user_id>` | 调整权限与有效期 / 移除 |

### 存储后端

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET/POST | `/me/backends`、`PATCH/DELETE /me/backends/<id>` | 登录 | 用户自己的存储（`allow_user_backends` 开启时生效） |
| GET/POST | `/backends`、`PATCH/DELETE /backends/<id>` | admin | 系统后端：优先级、启停、`visibility`（`public`/`private`）、每后端配置 |

`visibility=private` 表示桶是私有读：该后端的直链不对外使用，所有访问经 `/raw/<sha>` 由驱动签发临时读地址后转发；
驱动没有 `upimg_url` 时保存会 400。列表项同时返回 `visibility` 与 `private_readable`。

### 站点、钩子与运维

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/site` | 匿名 | 前台展示字段（站点名、公告、上传限制等） |
| GET/PUT | `/settings` | admin | 站点设置 |
| GET | `/settings/version` | admin | 版本检测（`?refresh=1` 跳过缓存） |
| POST | `/settings/smtp/test` | admin | 发测试邮件 |
| GET/PATCH/DELETE | `/users`、`/users/<id>` | admin | 用户列表（`page` / `page_size`，默认 15）/ 审核与禁用 / 删除 |
| GET | `/health` | 匿名 | 存活探针 |

钩子相关接口见[钩子基础契约](extend/contract.md)的「相关接口」一节。
