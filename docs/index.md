# sapic 文档

sapic 是一个自建图床：后端是 API-only 的 Flask 应用（`server/`，包名 `sapic`），
前端是独立的 Vue 3 + Vite 应用（`web/`），元数据存关系库（Peewee + PostgreSQL / MySQL / SQLite），不需要 Redis。

**存储后端和登录方式都是扩展点**：一个第三方 pip 包声明 `__catalog__` 并实现约定的函数，
就能作为存储驱动或登录 Provider 接入，核心代码不需要改动。这部分契约见
[扩展开发](extend/index.md)。

```{note}
本目录是 v2 的文档。v1 代码已不在仓库里，从 v1 升级见 `DEPLOY.md` 的数据迁移一节。
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
