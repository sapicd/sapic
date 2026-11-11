# 变更记录

## 2.0.0-pre — 2026-11-11

首个 v2 预发布。相对 v1 是一次重写：后端拆成 API-only 的 Flask 应用（`server/`，Peewee + 关系库），
前端独立为 Vue 3 SPA（`web/`），存储后端与登录方式全部插件化。安装与升级步骤见 `DEPLOY.md`，
接口细节见 `docs/api.md`。

### 新增

**图片**

- 图片有效期：上传传 `expire`，之后可用 `expire_at` 调整；到期后立即按不存在处理，并在后台
  硬删除文件与记录（请求期节流兜底 + `flask sa purge-expired`）。
- 批量操作：批量删除、移动相册、改可见性、发布到广场（单次 ≤100 张）。
- 关键词与标签筛选；图片导入外链（只登记 `source_url`，不下载文件）。
- 视频上传与播放：列表/广场按首帧做封面，详情页原生播放器。
- 上传时剥离 EXIF/XMP（拍摄时间、相机、GPS 不落存储），只从文件头读宽高。

**相册与可见性**

- 相册成为实体：公开 / 私有 / 共享三档，单图可覆盖相册可见性。
- 共享成员按用户名授权 `read` / `write`，可设有效期；过期即失效。
- 默认相册（新用户注册时创建）与系统相册（匿名上传归入，仅管理员可见于全站视图）。

**账号**

- 访问令牌（PAT）分 `read` / `upload` / `write` / `admin` 四档 scope，逐请求生效。
- 邮箱验证、注册审核（通过 / 拒绝 + 拒绝理由 + 通知邮件）、自助注销（需密码 + 名下无图）。
- 头像上传与服务端裁剪；OIDC 统一登录（`passport` 钩子），支持绑定 / 解绑。
- Cookie 会话的写操作强制 `X-CSRF-Token`。

**扩展与运维**

- 钩子用声明式 JSON 描述后台界面（manifest / 插槽 / action / dataset），前端按词表渲染。
- 后台可安装、启停、重载第三方钩子包，并提供官方市场；存储后端支持多实例、优先级与异步副本。
- 多阶段 Dockerfile（内置 nginx 托管静态文件）、`docker-compose.yml`（单容器 + SQLite）、
  `kube-sapic.yaml`（单副本 Deployment + Service）。
- `GET /api/v2/health` 健康检查（数据库不通返回 503）、后台版本更新检测。
- 个人设置（油猴开关、背景图与透明度）、按用户配置的防盗链。

### 变更

- 上传端点：`POST /api/upload` → `POST /api/v2/upload`（字段 `file` 或 `url`，取 `data.image.src`）。
- 鉴权：`Authorization: Token` → `Authorization: Bearer <PAT>`；`admin` scope 仅管理员可申请。
- 图片地址：`/static/...` → 公开图直连存储后端，私有图与无直链后端走 `/raw/<sha>`（支持 Range）。
- 图片列表是**个人图库**语义：只含自己的图片与共享给自己的相册，他人公开图不再出现在列表里。
- 公告由白名单富文本改为纯文本；命令行只剩 `flask sa upgrade` / `create-admin` / `purge-expired`。
- 界面固定中文，不再引入 v1 的翻译机制。

### 移除

- 个人 RSS（`/feed`）：匿名聚合出口会暴露「谁有哪些图、何时上传」。
- v1 的 `/api/upload` 兼容层：客户端按 `docs/usage.md` 改配一次即可。
- LinkToken 分权引用与调用统计（由 PAT + 相册共享替代）。
- `sendmail` / `token` 钩子与 `/api/extendpoint` 开放端点（分别由内置 SMTP、PAT 与声明式 action 取代）。
- 上传后端分组、每用户上传配额、自定义路径/文件名规则、用户标签编辑、留言板与站内消息。
- 仓库不再包含 v1 代码（`V1/`），历史版本见 git tag。

### 升级注意

- v1 → v2 数据迁移：`tools/migrate_v1_to_v2.py`（幂等、支持 `--dry-run`，保留原 `sha`，
  已发布的 `/raw/<sha>` 与直链继续有效），用法见 `DEPLOY.md` 7.1。
- 客户端（PicGo / uPic / ShareX / uTools / Typora / 右键菜单 / 油猴）需改一次配置，逐项见
  [docs/usage.md](./docs/usage.md)。
- 生产必须配置 `sapic_secretkey`，否则启动即失败；多进程 / 多副本请用 PostgreSQL 或 MySQL。
