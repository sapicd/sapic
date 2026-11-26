# 常见问题

按症状归类的排查表。先做这三件事，多数问题能自己定位：

- `GET /api/v2/health`：返回 503 就是数据库不通（DSN 写错、库没起、账号无权限）。
- 看响应头 / 响应体里的 `request_id`，在服务端日志里搜同一个值，能拿到完整堆栈。
- 后台 `/admin/setting` 里的开关与上限，往往就是「为什么不行」的答案。

## 部署与启动

| 现象 | 原因与处理 |
| --- | --- |
| 启动报 `STORAGE_DIR must be an absolute path` | 配置里写了相对路径，改成绝对路径（容器内是 `/app/server/data/upload`） |
| `/api/v2/health` 返回 503 | 数据库连不上：核对 `sapic_db_url`、库是否启动、账号权限与库名 |
| 前端刷新页面 404 | nginx 缺 SPA 回退：`try_files $uri $uri/ /index.html` |
| 图片直链、邮件里的链接是内网地址 | 没设 `sapic_external_base_url`，反代/网关后面必须设成对外地址 |
| 静态资源 404 / 拿到旧页面 | `index.html` 被长缓存了；应 `Cache-Control: no-store`，只有 `/assets/` 可以长缓存 |
| 容器重建后数据没了 | 没挂 `/app/server/data`；库文件、上传文件与钩子包都在这里 |

## 登录与会话

| 现象 | 原因与处理 |
| --- | --- |
| 登录成功但刷新就掉线 | 反代没传 `X-Forwarded-Proto` 或没开 `sapic_proxyfix=1`，Cookie 的 `Secure` 与站点协议不一致 |
| OIDC 回调 400 `invalid oidc state` | 回调域名/协议与发起时不一致：检查 `sapic_proxyfix`、外层 TLS 透传与 OIDC 服务端登记的回调地址 |
| 登录提示账号未激活 | `status=1` 与待审核（`-1`）能登录；已拒绝 / 已禁用不行，管理员在 `/admin/users` 处理。待审核账号可正常浏览，只是不能上传图片 |
| 关闭密码登录后进不去了 | `password_login` 关掉前要先把管理员账号绑定 OIDC；已锁死则直接改库里的站点设置 |
| `invalid csrf token` | 拿浏览器会话当令牌用了；客户端一律用 PAT |

## 上传

| 现象 | 原因与处理 |
| --- | --- |
| 413 / `file exceeds N MB` | 三层取最小值：nginx `client_max_body_size`、`sapic_maxupload`、站点 `upload_image_max_size` / `upload_video_max_size`，改大时一起改 |
| `file type is not allowed` | 后台「上传后缀白名单」`upload_allowed_ext` 没放开该后缀；视频还要开 `allow_video` |
| `{"code":"FORBIDDEN","message":"anonymous upload is disabled"}` | 请求没带令牌，或站点关闭了匿名上传 |
| `{"code":"UNAUTHORIZED","message":"invalid token"}` | 令牌填错、已撤销或已过期，重新建一枚 |
| `token scope does not allow upload` | 令牌没勾「上传图片」 |
| 客户端报「找不到图片地址」 | JSON 路径填错：v2 信封是 `data.image.src`，不是 `src` |
| URL 上传报 `remote fetch failed` | 服务端抓取只接受域名（IP 字面量直接拒）、不跟随重定向；内网地址会被拦，管理员才可用站点代理兜底 |
| 上传成功但状态码不是 200 | 上传成功返回 **201**；有的客户端把 201 当失败，按 `code: "OK"` 判断 |

## 图片访问

| 现象 | 原因与处理 |
| --- | --- |
| 访问 `/raw/xxx` 返回 404 | 图片已删除/已过期，或副本已不在对应后端（查 `image_backends.state`） |
| 上传成功但链接打不开 | 图片在私有相册或私有读的后端：需登录后经 `/raw/<sha>` 访问，直链不对外 |
| 自己站点能看、别人引用时 403 | 该图开了 Referer 校验；把引用方域名加进「允许引用的域名」，或关掉该开关 |
| 管理员在图库里看不到别人的公开图 | 个人图库只含自己的与共享的；看全站要显式切「全站」视图（`scope=all`，只有公开图） |

## 后台与扩展

| 现象 | 原因与处理 |
| --- | --- |
| 后台看不到钩子 | 模块没被登记或 import 失败：`HOOK_PKG_STORAGE_DIR` 只加入 `sys.path`、**不扫描目录**，要在钩子页登记模块名；导入异常看日志里的 traceback |
| 后台安装扩展报 `HOOK_PKG_STORAGE_DIR is not configured` | 该项被置空，填回目录（默认 `server/data/hooks`）并确保运行用户可写 |
| 改了钩子代码没生效 | 调一次重载（`POST /api/v2/hooks/reload` 或钩子页的「重载」），不用重启进程 |
| 钩子市场列表加载失败 | 出网被拦或 GitHub 不可达；用 `sapic_hookmarketurl` 指向镜像，或在市场页「手动安装」直接填包名 |
| 后台看不到「可更新」 | `sapic_updatecheckurl` 被置空（纯内网部署），或上游接口不可达 |
| 管理员接口一律 404 | 用的是普通账号；后台路由对非管理员渲染 404，不提示无权限 |

写钩子时遇到的具体问题（插槽不出现、按钮没反应、配置存不上）见
[钩子基础契约](extend/contract.md)；本页只管「服务本身不对劲」。
