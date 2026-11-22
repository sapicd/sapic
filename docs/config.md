# 配置

配置分两层：**进程级配置**决定服务怎么跑，**站点设置**决定业务行为。

## 进程级配置

来源优先级：类默认值 → `server/.cfg`（`k=v` 每行一条）→ 环境变量，最后统一校验
（`sapic/basis/conf.py`）。环境变量统一前缀 `sapic_`。

| 配置项 | 环境变量 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `ENV` | `sapic_env` | `production` | `dev` 启用开发默认值（DEBUG、内置密钥） |
| `SECRET_KEY` | `sapic_secretkey` | 内置随机串 | Cookie 签名密钥，≥ 14 字节；可选。容器镜像不传时 entrypoint 会生成并持久化到数据目录（`SAPIC_SECRET_FILE`）；非容器部署空值仍用内置公开串，公网多用户建议替换 |
| `DATABASE_URL` | `sapic_db_url` | `sqlite:///<server>/data/sapic.db` | `postgresql://` / `mysql://` / `sqlite:///` |
| `MAX_UPLOAD` | `sapic_maxupload` | `25` | 整个请求的硬上限（MB）→ `MAX_CONTENT_LENGTH` |
| `STORAGE_DIR` | `sapic_storagedir` | `<server>/data/upload` | 本地存储根目录，相对路径按 `server/` 归一 |
| `SESSION_TTL` | `sapic_session_ttl` | `604800` | 会话有效期（秒），最小 60 |
| `PROXY_FIX` | `sapic_proxyfix` | `false` | 信任 `X-Forwarded-*` |
| `LOG_LEVEL` | `sapic_loglevel` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOG_DIR` | `sapic_log_dir` | `<server>/data/log` | 应用日志 `sys.log` 所在目录；置空只输出到标准错误 |
| `HOOK_PKG_STORAGE_DIR` | `sapic_hookpkgstoragedir` | `data/hooks` | 第三方钩子包目录（`pip install --target` 目标），置空关闭后台安装 |
| `HOOK_MARKET_URL` | `sapic_hookmarketurl` | 官方 list.json | 钩子市场数据源，可换镜像 |
| `UPDATE_CHECK_URL` | `sapic_updatecheckurl` | 官方发布接口 | 版本检测数据源，置空即关闭（内网部署） |
| `EXTERNAL_BASE_URL` | `sapic_external_base_url` | 空 | 给图片直链加前缀，空则按当前请求的域名补全 |
| `SCHEDULER` | `sapic_scheduler` | `true` | 进程内跑后台任务（到期清理、审核扫描、演示账号改密）；多 worker 用文件锁选主，关掉后回到「请求时兜底清理」 |
| `SCHEDULER_PURGE_INTERVAL` | `sapic_scheduler_purge_interval` | `600` | 过期清理间隔（秒），最小 10 |
| `SCHEDULER_REVIEW_INTERVAL` | `sapic_scheduler_review_interval` | `300` | 审核扫描间隔（秒），最小 10；没有启用的 `moderator` 钩子时这趟直接跳过 |

排查环境变量是否写对时，直接打印最终生效的配置：

```bash
cd server && ../.venv/bin/python -c "import json; from sapic.basis.conf import load_config; print(json.dumps(load_config(), indent=2, ensure_ascii=False))"
```

本地没有 `server/.cfg` 也能直接跑（默认 SQLite + 内置密钥）；想切换到开发默认值
（DEBUG、DEBUG 日志）时在命令前加 `sapic_env=dev`。

## 站点设置

存在 `settings` 表，默认值与校验集中在 `sapic/libs/settings.py` 的 `DEFAULTS`，
后台「站点设置」页（`PUT /api/v2/settings`，仅管理员）维护，可写键与类型校验在
`sapic/views/settings.py`。前台通过 `GET /api/v2/site` 读取展示字段。

| 分组 | 键 |
| --- | --- |
| 站点展示 | `site_name`、`site_keywords`、`site_description`、`site_logo`、`site_background`、`site_background_mobile`、`site_background_opacity`、`site_icp`、`site_footer`、`site_announcement`、`login_notice` |
| 上传 | `allow_anonymous_upload`、`upload_notice`、`upload_allowed_ext`、`upload_image_max_size`、`upload_video_max_size`、`upload_count_limit`、`allow_video`、`upload_fetch_proxy`（URL 抓取代理，见下） |
| 有效期 | `image_expire_default_days`、`image_expire_max_days`（0 表示不启用规则） |
| 存储 | `storage_replica`（多副本）、`allow_user_backends`、`user_backend_limit` |
| 注册与账号 | `allow_register`、`register_review`、`password_login`、`forbidden_username`、`default_album_visibility` |
| 演示账号 | `demo_rotate_enabled`、`demo_rotate_username`、`demo_rotate_password`、`demo_rotate_interval`（秒，60～86400） |
| 广场 | `plaza_enabled`（默认关） |
| 邮件 | `smtp`（`{host, port, user, password, from, tls}`，`tls` 表示 STARTTLS；端口 465/994 自动走隐式 SSL，不要勾 `tls`）。启用并配好 `mail` 类钩子（如 `sendcloud`）时优先走钩子，SMTP 只作兜底 |
| 钩子 | `hooks_state`、`hooks_config`、`hooks_imported`（由钩子接口写入，不走键白名单） |

几个容易踩的点：

- `upload_fetch_proxy` 是**兜底**代理：直连拿到可用图片就不碰它，只有这一次直连「没拿到可用响应」
  才用它重试一次——包括超时 / 连接错误 / 本地解析不了，以及被反爬或地区限制时边缘节点直接回的
  4xx/5xx、还有 200 但内容是 HTML 的拦截页。填一个 `http://` 或 `https://` 代理地址，需要认证写
  `http://user:password@host:port`；socks 不支持（`urllib` 只认 http/https）。
  目前只有 URL 上传的服务端抓取会用到它，存储后端的内部地址永远直连。
  两次都失败时错误消息带原因（如 `remote fetch failed: http 403` / `... : network error`），
  服务端日志里还有一行 `direct url fetch failed (...), retrying via proxy` 说明确实兜底了。

- `upload_count_limit` 是**单次批次**的前端队列限制，后端每次请求只处理一个文件，
  想限制「每天能传多少」要另立语义。
- `image_expire_max_days` 一旦大于 0，就不允许再创建永久图片，未指定时按上限处理。
- `allow_video` 关掉后视频后缀直接拒收；后缀白名单仍是第一道门。
- `upload_allowed_ext` 默认**不含 `svg`**：SVG 能在同源执行脚本，只有明确加回才允许上传
  （本地上传、头像与外链导入同一口径），并且 `/raw/<sha>` 对 SVG 一律返回
  `Content-Disposition: attachment` + `application/octet-stream`，不会在站点源下渲染。
- `password_login` 关掉后本地登录与注册接口直接 403，只剩统一登录入口。
- 演示账号轮换只在开关打开、用户名和密码都填了时生效：调度器按 `demo_rotate_interval`
  把该本地账号的密码重置回配置值（登录名统一转小写），同时吊销它的会话与 PAT。
  账号不存在、或目标恰好是管理员时跳过——后者是为了避免把后台锁死。它不会创建账号；
  密码读取只回掩码，把掩码原样回传表示不改。
- `site_announcement`（全站公告）只解析三种排版：`**加粗**`、`[文字](https://链接)`、
  空行分段（单换行也换行）。链接只认 `http(s)://` 与 `mailto:`，其余写法按原文显示；
  它是纯文本语法，**不执行任何 HTML 标签**（前端用节点构造渲染，没有 `v-html`）。
- 新增配置项必须同时接进「后台表单 + 实际生效点」，不要留下只存不用的开关。
