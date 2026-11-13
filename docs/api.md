# API 参考

```{note}
**接口详情以在线文档为准**：`GET /api/v2/docs` 是 Swagger UI（可交互、可试请求），
文档源是 `GET /api/v2/openapi.json`（OpenAPI 3.0，可直接导入 Apifox / Postman /
Insomnia）。本文只保留跨接口的约定、鉴权流程与业务规则——**路径、参数、请求体、响应
字段一律以在线文档为准**，不要在这里重复维护。
```

## 约定

- 业务接口前缀 `/api/v2`，请求与响应都是 JSON（上传除外，走 `multipart/form-data`）。
- 根路径上还有两个不属于 `/api/v2` 的端点：`GET /raw/<sha>`（图片输出，已发布直链的兜底）
  与 `GET /i/<sha>`（旧版直链，跳转到 `/raw/`）。油猴脚本在 `/api/v2/userscript.user.js`。
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

两种方式，任选其一；全局 CSRF 中间件没有任何端点例外。

1. **会话 Cookie**（浏览器）：先 `GET /api/v2/auth/csrf` 拿 CSRF 令牌，
   写操作（POST/PUT/PATCH/DELETE）带 `X-CSRF-Token` 请求头。登录成功后
   `POST /auth/login` 的响应里也会返回最新令牌；改密码会吊销其它会话并换发新令牌。
2. **个人访问令牌（PAT）**：`Authorization: Bearer sp_xxxxxxxx`。令牌有四档 scope：
   `read`（安全方法）、`upload`（上传）、`write`（其它改动）、`admin`（管理接口），
   缺省 `read` / `upload` / `write`；`admin` 只有管理员能申请。

客户端（PicGo / uPic / Typora 等）带不了 CSRF 头，一律用 PAT，配置方式见[快捷上传](usage.md)。

**权限边界**：

- 只有 `status=1`（正常）的账号能登录、持有会话或使用 PAT；待审核、已拒绝、禁用一律无效。
- PAT 创建时可选 `album_id`（上传默认相册）：上传不带 `album_id` 时落到它，相册被删或
  失去写权限后回落到用户默认相册；请求里显式传的 `album_id` 永远优先。
- 上传接口允许匿名（站点 `allow_anonymous_upload` 打开时），所以它不用登录装饰器，
  而是在视图内单独校验 `upload` scope。
- 站点在后台关闭 `upload_enabled` 后，`POST /upload` 对所有凭据返回 403——只冻结新增，
  已有图片的访问、编辑与删除不受影响。

在 Swagger UI 里点 **Authorize** 填 PAT 即可试请求；用浏览器会话试写接口时页面会自动补
`X-CSRF-Token`。

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

## 资源概览

只说明「有哪些资源、归谁所有」，字段与参数看在线文档。下表的 API 端点省略了 `/api/v2`
前缀（例如 `/site` 即 `GET /api/v2/site`），只有「直链」一行是根路径：

| 资源 | 端点 | 语义 |
| --- | --- | --- |
| 站点 | `/site`、`/health` | 匿名：前台展示配置、存活探针 |
| 认证 | `/auth/*` | 会话、注册登录、邮箱验证、OIDC 绑定、个人偏好、PAT |
| 上传 | `/upload` | `file` 或 `url` 二选一，成功 201 返回 `{image}` |
| 图片 | `/images*`、`/plaza` | 个人图库的查询与维护；广场是匿名曝光渠道 |
| 相册 | `/albums*` | 相册与共享授权（成员、权限、有效期） |
| 存储 | `/backends`（admin）、`/me/backends` | 系统后端；用户自己的后端（`allow_user_backends` 开启时生效） |
| 运维 | `/settings*`、`/users`（admin） | 站点设置、版本检测、用户审核与禁用 |
| 直链 | `/raw/<sha>`、`/i/<sha>` | 已发布图片的公开地址（根路径，不在 `/api/v2` 下） |
| 文档 | `/docs`（Swagger 页面）、`/openapi.json`（OpenAPI 源） | 即 `GET /api/v2/docs` 与 `GET /api/v2/openapi.json`，见文首「在线文档」 |

钩子相关接口见[钩子基础契约](extend/contract.md)的「相关接口」一节。

## 可见性与地址

可见性的维度是**相册**，单张图片可以覆盖：

- 每张图片都必须属于一个相册；`images.visibility` 为 `null` 表示跟随相册，为
  `public` / `private` 时覆盖相册。图片不能被摘出相册（`PATCH` 传空 `album_id` 直接 400），
  否则「无相册 + 无覆盖」会被当成公开而泄漏。
- 登录用户上传落到**默认相册**（可见性取站点设置 `default_album_visibility`），匿名上传落到
  **系统相册**（管理员能在相册列表里看到 `role=system` 那条，用于筛选匿名图片）。
- 图库列表只含自己的图片 + 共享给自己的相册。**管理员也是个人图库**，要看全站必须显式传
  `scope=all`；该视图只放大到公开图片，别人的私有相册不会出现。非管理员传该参数 403。
- `src` 已按可见性处理：公开图给存储直链（后端没配 `domain` 时回落到 `/raw/<sha>`），
  私有图固定 `/raw/<sha>`。存储后端 `visibility=private`（私有读桶）时直链不对外使用，
  所有访问都经 `/raw/<sha>` 由驱动签发临时读地址后转发。
- 广场（`/plaza`）默认关闭，`plaza_enabled` 关掉时直接 404。只有可见性为 `public` 且经
  相册开关 + 单图三态显式发布的图片才进列表。
- 图片有效期用 `expire`（秒）在**上传时**确定，省略取站点默认、0 表示永久，上限由站点设置
  控制；之后通过 `PATCH` 的 `expire_at`（绝对时间戳）调整。
