# sapic

自建图床：后端是 API-only 的 Flask 应用（`server/`，包名 `sapic`），前端是独立的 Vue 3 单页应用（`web/`）。
元数据存关系库（PostgreSQL / MySQL / SQLite），**存储后端与登录方式都是插件**，
一个第三方 pip 包就能接入新的对象存储或第三方登录，核心代码不需要改。

[![Actions Status: ci](https://github.com/sapicd/sapic/workflows/ci/badge.svg)](https://github.com/sapicd/sapic/actions?query=workflow%3A%22build+and+test%22)
[![codecov](https://codecov.io/gh/sapicd/sapic/branch/master/graph/badge.svg)](https://codecov.io/gh/sapicd/sapic)
![Last Release](https://img.shields.io/github/release/sapicd/sapic.svg?style=flat-square)

## 特性

- **上传**：拖拽、粘贴、远程 URL（服务端抓取）、批量队列；图片与视频分别限制后缀与大小，支持有效期。
- **图片管理**：游标分页列表、关键词与标签筛选、批量移动/可见性/删除、分享模板（URL / HTML / Markdown / rST）。
- **相册与可见性**：权限以相册为维度（公开 / 私有 / 共享），按用户名共享并授予读写权限与有效期，单图可覆盖。
- **存储**：多后端 + 优先级 + 副本；内置本地 / 七牛 / 又拍云 / GitHub / Gitee。
- **账号**：注册审核、邮箱验证、找回密码、OIDC 统一登录；访问令牌分 `read` / `upload` / `write` / `admin` 四档。
- **扩展**：钩子用声明式 JSON 描述后台界面，第三方包可在后台安装、启停、单后端独立配置。
- **客户端接入**：PicGo / uPic / ShareX / uTools / Typora / 油猴脚本统一走 `POST /api/v2/upload` + PAT。

## 快速开始

```bash
git clone https://github.com/sapicd/sapic && cd sapic

python3 -m venv .venv                        # 依赖装在仓库根的 .venv，make 会自动识别
make setup                                   # 后端依赖 + 前端 pnpm install
make create-admin U=admin P='你的密码'        # 创建管理员
make dev                                     # 后端 http://127.0.0.1:9514
make web-dev                                 # 另开终端：前端 http://127.0.0.1:5173
```

Docker 一行起（单容器 + SQLite）：

```bash
SAPIC_SECRET_KEY=$(openssl rand -hex 32) docker compose up -d
```

生产模式必须显式配置 `sapic_secretkey`（内置默认密钥是公开字符串，会被直接拦下）。
完整的安装、反代、容器与集群部署、从 v1 迁移数据见 **[DEPLOY.md](./DEPLOY.md)**。

## 文档

线上文档：<https://sapic.rtfd.vip>　本地构建：`make docs`（产物在 `docs/_build/html`）。

| 内容 | 位置 |
| --- | --- |
| 介绍与截图 | [docs/intro.md](./docs/intro.md) |
| 安装部署 | [docs/install.md](./docs/install.md)、[DEPLOY.md](./DEPLOY.md) |
| 快捷上传（PicGo / uTools / Typora / 右键菜单 / 油猴） | [docs/usage.md](./docs/usage.md) |
| 命令行工具 sapicli | [docs/cli.md](./docs/cli.md) |
| 配置项 | [docs/config.md](./docs/config.md) |
| API 参考 | [docs/api.md](./docs/api.md) |
| 扩展开发（钩子、存储驱动、登录 Provider） | [docs/extend/](./docs/extend/index.md) |
| 架构说明 | [ARCH.md](./ARCH.md) |
| 本地开发、测试与代码风格 | [docs/dev.md](./docs/dev.md) |
| 后端 / 前端内部说明 | [server/README.md](./server/README.md)、[web/README.md](./web/README.md) |
| 变更记录 | [CHANGELOG.md](./CHANGELOG.md) |

从 v1 升级请先看 [DEPLOY.md](./DEPLOY.md) 的数据迁移一节（保留原 sha，老链接继续有效）。

## 演示站

<https://sapicd.com>，测试账号 `demo` / `123456`（请勿修改密码）。

对外开放，为防止乱传已关闭匿名上传；随意注册，但不可用于非测试用途，图片保留删除权利。

## Contributing

欢迎提交 issue 与 PR，开发约定、测试与提交前检查见 [docs/dev.md](./docs/dev.md)。

<a href="https://github.com/sapicd/sapic/graphs/contributors">
  <img src="https://opencollective.com/sapic/contributors.svg?width=890&button=false" />
</a>

## License

[BSD 3-Clause](./LICENSE)
