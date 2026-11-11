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

```{note}
当前版本 **2.0.0-pre**（v2 重写版）。相对 v1 的变化：后端改为 API-only + Peewee、前端独立为
Vue 3 应用、运行时不再依赖 Redis；v1 代码不再随仓库发布（历史版本看 git tag）。
升级步骤见仓库根的 `DEPLOY.md` 第 7 节，逐项变化见 `CHANGELOG.md`。
```

```{toctree}
:maxdepth: 2
:caption: 使用

intro
install
usage
cli
config
```

```{toctree}
:maxdepth: 2
:caption: 扩展开发

extend/index
extend/contract
extend/provider
extend/storage
extend/publishing
```

```{toctree}
:maxdepth: 2
:caption: 参考

api
dev
```
