# 打包、发布与安装

## 包的形态

一个扩展就是一个可导入的模块或包，**入口不需要 entry_points**：sapic 按模块名加载，
模块里的元数据与函数就是全部契约（见[钩子基础契约](contract.md)）。

```text
sapic_storage_s3/
├── pyproject.toml
└── sapic_storage_s3/
    └── __init__.py     # __version__ / __author__ / __catalog__ + 契约函数
```

要点：

- **模块名就是钩子名**，也是 Provider 的 URL 片段（`/auth/oidc/<name>`）、
  `hooks_state` / `hooks_config` 的键、后端行的 `hook_name`。改名等于换一个插件。
- `__version__` 与 `__author__` 必填，否则模块会被跳过（日志里有 warning）。
- 只能声明自己实现的目录：`auth` / `upload` / `processor`，其余视为纯界面钩子。
- 依赖要在代码里做 `try/except ImportError` 降级，并在 `hook_manifest()` 的 `help`
  或 action 返回值里给出「请安装 X」的提示。`base.txt` 只装官方内置钩子用到的 SDK，
  第三方钩子的依赖由你自己的包声明，不要指望 sapic 替你装。
- 一个包只暴露一个钩子；要同时提供驱动与界面块，用同一个模块的 `hook_manifest()` 声明。

## 安装

### 后台安装（推荐）

```text
POST /api/v2/hooks/install      {"package": "sapic-storage-s3==0.1.0", "module": "sapic_storage_s3"}
```

等价于 `pip install --target $HOOK_PKG_STORAGE_DIR <package>`，超时 180 秒。
`module` 可以省略：包目录名与模块名一致时扫描即命中，否则需要再调
`POST /api/v2/hooks/import` 登记模块名。安装失败会返回 `ok: false` 与 pip 日志。

`HOOK_PKG_STORAGE_DIR`（默认 `data/hooks`，`sapic_hookpkgstoragedir` 可改）：
只加入 `sys.path`、不参与目录扫描——`pip install --target` 会把依赖一起丢进去，
扫描它们等于执行无关代码。

### 手动安装

```bash
pip install --target ./data/hooks sapic-storage-s3
# 或直接装进解释器 site-packages
```

然后登记模块名（后台「钩子 → 导入」或接口）：

```text
POST /api/v2/hooks/import       {"module": "sapic_storage_s3"}
```

管理已安装包：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v2/hooks/packages` | 包目录里 `*.dist-info` 对应的包与版本 |
| DELETE | `/api/v2/hooks/import/<module>` | 停止加载（`?purge=1` 连包文件一起删） |
| POST | `/api/v2/hooks/install` | 安装/升级（`upgrade: true`）并可选自动登记 |

## 市场清单

`GET /api/v2/hooks/market` 读 `sapic_hookmarketurl` 指向的 JSON 数组（默认官方
`list.json`，6 小时缓存），字段如下：

| 字段 | 说明 |
| --- | --- |
| `name` | 展示名 |
| `module` | 模块名，用于合并本地「已加载/已安装」状态 |
| `desc` / `author` | 说明与作者 |
| `github` | 仓库，可只写 `owner/repo` |
| `pypi` | 包名，支持 `$name` 占位 |
| `home` | 主页，缺省用 github |
| `status` | 自定义标记（如 `beta`） |

市场只是数据源：装什么、启用什么仍以 `hooks_imported` / `hooks_state` 为准。

列表由服务端分页，长列表不会一次性推给浏览器：

```text
GET /api/v2/hooks/market?page=2&page_size=10
```

```json
{
  "items": [],
  "total": 23,
  "page": 2,
  "page_size": 10,
  "pages": 3,
  "updated_at": 1790000000,
  "market_url": "…",
  "storage_dir": "…",
  "configured": true
}
```

`page` 从 1 开始，越界会收敛到最后一页；`page_size` 默认 10、上限 100；
非数字参数返回 `PARAM_ERROR`。`installed` / `loaded` / `enabled` 只对当前页的条目合并。

## 调试与排查

```text
GET  /api/v2/hooks                     # 清单：kind / warnings / family / version
GET  /api/v2/hooks/manifests           # 含未启用的全部清单（admin）
POST /api/v2/hooks/reload              # 改完代码/装完包后立即重载
GET  /api/v2/hooks/slots/<slot>        # 直接看插槽渲染出来的节点
POST /api/v2/hooks/<name>/actions/<action>
GET  /api/v2/hooks/config              # 配置字段与已保存的值
```

常见现象：

| 现象 | 原因 |
| --- | --- |
| 钩子列表里没有它 | 缺 `__version__` / `__author__`，或模块名没登记、不在 `sys.path` |
| 出现了但 `kind` 是 `ui` | 没声明 `__catalog__`，核心不会把它当驱动/Provider |
| `warnings` 提示缺函数 | 声明了 `upload` 却缺 `upimg_save`，或 `auth` 缺两个契约函数 |
| 后端列表里没有它 | 钩子未启用，或缺 `upimg_save`；启用后需要一次 `GET /backends` 触发 `sync_backends` |
| 选「私有」保存报 400 | 驱动没实现 `upimg_url`（`driver cannot read private objects`），先补读契约或改用公开直链 |
| 登录页没有按钮 | Provider 的 `slot_login_after_form` 在配置不全时返回空，填完 client_id 再看 |

日志用 `logging.getLogger(__name__)`，不要 `print()`；钩子抛异常不会拖垮整个请求，
但会记录堆栈并按 `code=1` 处理，排查时先看服务端日志。
