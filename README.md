# sapic

自建图床。后端是 API-only 的 Flask 应用（`server/`），前端是独立的 Vue 3 单页应用（`web/`），
图片元数据存关系库（PostgreSQL / MySQL / SQLite），**存储后端与登录方式都是插件**，
一个第三方 pip 包就能接入新的对象存储或第三方登录，核心代码不需要改。

[![Actions Status: ci](https://github.com/sapicd/sapic/workflows/ci/badge.svg)](https://github.com/sapicd/sapic/actions?query=workflow%3A%22build+and+test%22)
[![codecov](https://codecov.io/gh/sapicd/sapic/branch/master/graph/badge.svg)](https://codecov.io/gh/sapicd/sapic)
![Last Release](https://img.shields.io/github/release/sapicd/sapic.svg?style=flat-square)

## 特性

- **上传**：拖拽、粘贴、远程 URL（服务端抓取）、批量队列；图片与视频分别限制后缀与大小，支持有效期。
- **图片管理**：游标分页列表、关键词与标签筛选、批量移动/可见性/删除、分享模板（URL / HTML / Markdown / rST）。
- **相册与可见性**：权限以相册为维度（公开 / 私有 / 共享），按用户名共享并授予读写权限与有效期，单图可覆盖。
- **存储**：多后端 + 优先级 + 副本（主后端同步写入、其余异步补齐）；内置本地 / 七牛 / 又拍云 / GitHub / Gitee。
- **账号**：注册审核、邮箱验证、找回密码、OIDC 统一登录、头像裁剪；访问令牌分 `read` / `upload` / `write` / `admin` 四档权限。
- **扩展**：钩子用声明式 JSON 描述后台界面，第三方包可在后台安装、启停、单后端独立配置，并带一个官方市场。
- **客户端接入**：PicGo / uPic / ShareX / uTools / Typora / 右键菜单 / 油猴脚本，
  统一 `POST /api/v2/upload` + PAT 鉴权，配置与脚本见[快捷上传](./docs/usage.md)。
- **移动端可用**：窄屏下顶栏收进抽屉、表单与弹窗按视口收缩。

## 快速开始

```bash
git clone https://github.com/sapicd/sapic && cd sapic

python3 -m venv .venv                        # 建议：依赖装在仓库根的 .venv，make 会自动识别
make setup                                   # 后端依赖 + 前端 pnpm install
make create-admin U=admin P='你的密码'        # 创建管理员
make dev                                     # 后端 http://127.0.0.1:9514
make web-dev                                 # 另开终端：前端 http://127.0.0.1:5173
```

前端开发服务器会把 `/api` 与 `/raw/` 代理到 9514，直接访问 5173 即可。
生产部署则是先 `make web-build` 出 `web/dist`，再由 nginx 托管静态文件并反代后端：

```bash
make install-prod
make web-build
sapic_secretkey="$(openssl rand -hex 32)" make serve WORKERS=4
```

> 生产模式必须显式配置 `sapic_secretkey`（`server/.cfg` 或环境变量），
> 内置默认密钥是公开字符串，用它启动会被直接拦住。

### Docker

```bash
SAPIC_SECRET_KEY=$(openssl rand -hex 32) docker compose up -d     # 应用 + PostgreSQL
docker compose exec sapic sh -c \
  'cd /app/server && FLASK_APP=sapic python -m flask sa create-admin -u admin -p "你的密码"'
```

默认监听 80 端口（`SAPIC_PORT` 可改），数据在 `sapic-data` 卷里。
也可以 `make docker` 自行构建镜像，或 `kubectl apply -f kube-sapic.yaml` 部署到集群。

完整步骤、配置项与排错见 [DEPLOY.md](./DEPLOY.md)。

## 快捷上传

除了网页上传，sapic 还能被桌面工具和编辑器直接调用（先创建一个只含「上传图片」权限的访问令牌）：

| 场景 | 用法 |
| --- | --- |
| PicGo（桌面 / CLI） | 安装 `web-uploader` 插件，接口填 `https://你的站点/api/v2/upload`，字段名 `file`，取 `data.image.src` |
| uPic | macOS 菜单栏工具，添加「自定义」图床，API 地址 + 文件字段名 `file` |
| ShareX | Windows 截图工具，自定义上传目标（Form 表单 + `file`），响应取 `$.data.image.src` |
| uTools | 图床插件按 PicGo 同样方式配置，或用快捷命令调用 curl |
| Typora / VS Code / Obsidian | 走 PicGo 或自定义命令，图床配置复用上文 |
| sapicli（命令行） | Go 写的独立上传工具，批量上传 / 输出风格 / 剪贴板复制，见[命令行工具](./docs/cli.md) |
| Windows | OpenWithPlusPlus 右键菜单，`上传 → 复制链接` |
| macOS | 自动操作（Automator）快速操作，右键即可上传 |
| 油猴脚本 | 站点设置里开启后安装，`Alt` / `Ctrl` + 点击任意网页图片直接上传 |
| curl / 脚本 | `POST /api/v2/upload`（multipart，字段 `file` 或 `url`） |

每个工具的具体填写项与脚本见 **[快捷上传文档](./docs/usage.md)**。

## 文档

线上文档：<https://sapic.rtfd.vip>　本地构建：`make docs`（产物在 `docs/_build/html`）。

| 内容 | 位置 |
| --- | --- |
| 快捷上传（PicGo / uTools / Typora / 右键菜单 / 油猴） | [docs/usage.md](./docs/usage.md) |
| 命令行工具 sapicli | [docs/cli.md](./docs/cli.md) |
| 安装与部署 | [docs/install.md](./docs/install.md)、[DEPLOY.md](./DEPLOY.md) |
| 配置项 | [docs/config.md](./docs/config.md) |
| API 参考 | [docs/api.md](./docs/api.md) |
| 扩展开发（钩子、存储驱动、登录 Provider） | [docs/extend/](./docs/extend/index.md) |
| 架构说明 | [ARCH.md](./ARCH.md) |
| v1 → v2 功能对照 | [MIGRATION.md](./MIGRATION.md) |
| 贡献流程 | [CONTRIBUTING.md](./CONTRIBUTING.md) |

v1 的代码与文档归档在 `V1/`，仅供对照，不参与 v2 构建；从 v1 升级请先看
[DEPLOY.md](./DEPLOY.md) 里的数据迁移一节（保留原 sha，老链接继续有效）。

## 演示站

<https://sapicd.com>，测试账号 `demo` / `123456`（请勿修改密码）。

对外开放，为防止乱传已关闭匿名上传；随意注册，但不可用于非测试用途，图片保留删除权利。

## Contributing

欢迎提交 issue 与 PR，流程见 [CONTRIBUTING.md](./CONTRIBUTING.md)。

<a href="https://github.com/sapicd/sapic/graphs/contributors">
  <img src="https://opencollective.com/sapic/contributors.svg?width=890&button=false" />
</a>

## License

[BSD 3-Clause](./LICENSE)
