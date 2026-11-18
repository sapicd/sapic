# 贡献指南

感谢你的贡献！英文版：[CONTRIBUTING.md](./CONTRIBUTING.md)。

## 安全问题

**不要**为漏洞开公开 issue、PR 或 discussion，请按 [SECURITY-cn.md](./SECURITY-cn.md) 里的渠道私下上报。

## Bug 反馈

在 GitHub 新建 [Issue](https://github.com/sapicd/sapic/issues/new)，并尽量提供：

- 实际发生了什么，有完整异常堆栈就贴上来；
- 一个最小、完整、可验证的示例——它同时能说明问题出在 sapic 还是你的部署；
- Python、数据库、sapic 的版本（`GET /api/v2/health` 会返回版本与数据库状态），
  以及关键配置（贴之前把密钥打码）。

需要打印当前生效的后端配置时：

```bash
make config
```

## 功能需求

同样新建 [Issue](https://github.com/sapicd/sapic/issues/new)，请描述使用场景，而不只是你想要的实现方式。
非常欢迎直接提交 PR。

## 提交 PR

**开始之前**

- Fork <https://github.com/sapicd/sapic>，并保持与上游同步
  （[Syncing a fork](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/syncing-a-fork)）。
- 从 `dev` 分支切出，PR 也发往 `dev`，不要直接发到 `master`。

**环境**

```bash
make setup          # 后端开发依赖装进 .venv，前端 pnpm install
make dev            # 后端 0.0.0.0:9514，改代码自动重载
make web-dev        # 前端 127.0.0.1:5173，/api 与 /raw/ 代理到 9514
```

这些目标只是真实命令的封装（假定仓库根有 `.venv`、机器上有 `make`）。安装、容器与反代部署见
[DEPLOY.md](./DEPLOY.md)。

**编码**

遵循 [docs/dev.md](./docs/dev.md) 里的约定，要点：

- PEP 8、4 空格缩进、文件头 `# -*- coding: utf-8 -*-` + 英文模块 docstring，导入放文件头部
  （标准库 → 第三方 → 项目内）。
- Python 3.10+ 语法，新增函数带类型注解（`str | None`、`dict[str, Any]`）。
- 失败用 `ApiError(message, code)`，消息用英文；禁止裸 `except:`；日志走
  `logging.getLogger(__name__)`，不要 `print()`。
- 遵守依赖方向 `views → libs/utils → models/basis`，依赖 Flask 上下文的工具放 `utils/web.py`。
- 数据库结构变更走 `server/sapic/migrations/` 里的幂等迁移，不要用 `create_tables()` 改已有结构。
- 新增配置项必须同时接进「后台表单 + 实际生效点」。

**测试**

```bash
make test           # 或：cd server && python -m pytest -q
```

测试用临时 SQLite，不依赖外部服务。CI 跑 Python 3.10 / 3.12 / 3.13，
新增行为（尤其是扩展契约、解析、权限判定）请补对应用例。

**文档**

```bash
make docs           # Sphinx 构建到 docs/_build/html，warning 即失败
```

新增页面必须在 `docs/index.md` 的 `toctree` 里登记，否则不会被构建。

**变更记录与版本号**

同一个 PR 里在 [CHANGELOG.md](./CHANGELOG.md) 补一条精简记录，并同步
`server/sapic/version.py` 的 `__version__`。条目只写用户能感知的变化，
不要把实现细节和内部函数名堆进去。

**提交与 PR**

- 提交信息用约定式前缀，例如 `fix(images): keep the album on re-upload`、
  `docs: split the readme by language`。
- 不要把无关改动混进同一个提交；一个 PR 只做一件事，最好评审。

## 扩展开发

存储后端、登录 Provider 等钩子都是普通 pip 包，通过 [docs/extend/](./docs/extend/index.md) 里的契约接入。
发布到 PyPI 后，如果希望出现在后台的钩子市场里，开 issue 告诉我们。

## 许可

提交代码即表示同意以 [BSD 3-Clause](./LICENSE) 许可发布你的贡献。
