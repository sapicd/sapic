# sapic 文档

```{image} ../web/public/logo.png
:alt: sapic
:width: 220px
:align: center
```

sapic 是一个自建图床：后端是 API-only 的 Flask 应用（`server/`，包名 `sapic`），
前端是独立的 Vue 3 + Vite 应用（`web/`），元数据存关系库（Peewee + PostgreSQL / MySQL / SQLite），不需要 Redis。

**存储后端和登录方式都是扩展点**：一个第三方 pip 包声明 `__catalog__` 并实现约定的函数，
就能作为存储驱动或登录 Provider 接入，核心代码不需要改动。这部分契约见
[扩展开发](extend/index.md)。

## 我该看哪一页

| 你想做的事 | 从这页开始 |
| --- | --- |
| 先跑起来看看（Docker 一行 / 源码 5 分钟） | [快速开始](quickstart.md) |
| 部署到自己的服务器（systemd、nginx、HTTPS、备份） | [部署与运维](deploy.md) |
| 查进程级配置项、调站点设置 | [配置](config.md) |
| 接 PicGo / Typora / 右键菜单 / 油猴脚本 | [快捷上传](usage.md) |
| 从 v1 升级 | [从 v1 迁移数据](migrate-v1.md) |
| 写存储驱动 / 登录 Provider / 界面钩子 | [扩展开发](extend/index.md) |
| 出问题了 | [常见问题](faq.md) |

```{note}
当前版本 **2.0.0-pre.1**（v2 重写版）。相对 v1 的变化：后端改为 API-only + Peewee、前端独立为
Vue 3 应用、运行时不再依赖 Redis；v1 代码不再随仓库发布（历史版本看 git tag）。
逐项变化见 `CHANGELOG.md`。
```

```{toctree}
:maxdepth: 2
:caption: 开始

intro
quickstart
```

```{toctree}
:maxdepth: 2
:caption: 使用

install
deploy
config
usage
cli
migrate-v1
faq
```

```{toctree}
:maxdepth: 2
:caption: 开发

dev
extend/index
extend/contract
extend/provider
extend/storage
extend/moderator
extend/publishing
```

```{toctree}
:maxdepth: 2
:caption: 参考

api
```
