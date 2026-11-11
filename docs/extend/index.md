# 扩展开发总览

sapic 的插件叫**钩子（hook）**：一个 Python 模块或包，被核心按需加载，
用它自己声明的清单描述界面与能力。核心不认识任何插件名，只认契约。

## 三种扩展类型

扩展类型由 `__catalog__` 声明，契约判断集中在 `sapic/libs/ext.py`
（认证流程、存储解析、后台接口都问它，不各自 `getattr`）：

| `__catalog__` | kind | 必需函数 | 作用 | 核心落点 |
| --- | --- | --- | --- | --- |
| `auth` | `provider` | `oidc_authorize_url`、`oidc_exchange` | 第三方登录 | `views/auth.py` 的 `/auth/oidc/<name>` |
| `upload` | `driver` | `upimg_save`（`upimg_delete` 可选，私有桶还要 `upimg_url`） | 对象存储驱动 | `libs/storage.py` 的上传/副本/删除 |
| `processor` | `processor` | `upimg_stream_processor` | 上传前改写数据 | `libs/images.process_stream` |
| 其它/未声明 | `ui` | — | 只提供界面块与动作 | `libs/hook.py` 的插槽/动作/数据集 |

清单里的 `kind` 与 `warnings` 由核心计算：`warnings` 会点明「声明了 upload 却缺
`upimg_save`」这类不完整实现，后台钩子页与 `GET /api/v2/hooks` 都能看到。

## 加载与生效流程

1. **发现**：扫描包内 `server/sapic/hooks/*.py`（`family=local`），
   再按 `hooks_imported` 设置里的模块名 `import`（`family=third`，
   模块来自 `HOOK_PKG_STORAGE_DIR` 或已安装的 site-packages）。
2. **校验元数据**：缺 `__version__` / `__author__` 的模块被跳过并记日志，不影响其它钩子。
3. **启停**：`hooks_state` 里的布尔值优先，缺省看模块自己的 `__state__`（默认启用）。
4. **配置**：`hooks_config` 存钩子级配置，字段由 `hook_manifest()` 的 `config_schema` 声明，
   后台钩子页据此渲染表单（`PUT /api/v2/hooks/config/<name>`）。
5. **调用**：认证/存储/后处理按契约进入热路径；界面块、动作、数据集按前端请求触发。

钩子热重载：`POST /api/v2/hooks/reload` 立即重建快照；平时每隔
`HOOK_RELOAD_TIME` 按「源文件 mtime + 已登记模块列表」决定是否换快照，
多 worker 部署下任意进程改了启停/安装列表，其它进程也会跟上。

## 安装第三方包

两种方式都能把包交给 sapic（打包细节见 [发布与安装](publishing.md)）：

- **后台安装**（推荐）：`POST /api/v2/hooks/install`，等价于
  `pip install --target $HOOK_PKG_STORAGE_DIR <包名>`；如果包目录名与模块名不同，
  再用 `POST /api/v2/hooks/import` 登记模块名。
- **手动安装**：把包装进 `HOOK_PKG_STORAGE_DIR`（默认 `data/hooks`，已在 `sys.path` 上），
  或装进解释器的 site-packages，然后登记模块名。

该目录只加入 `sys.path`，**不参与扫描**：`pip install --target` 会把依赖一并丢进去，
按目录扫描会让无关第三方代码被当作钩子执行。

## 安全边界

- 安装、导入、删除、重载、读配置都是 admin 接口；钩子代码本身就是任意 Python，
  没有沙箱，装之前要信任来源。
- 钩子返回的界面是**声明式 JSON**，不是 HTML/JS。节点类型、键、`href` 协议、
  `action` 名、插槽名都在 `libs/ui.py` 白名单里清洗，未知内容直接丢弃，
  因此插件不能在前端注入脚本。
- 动作的 `scope` 由清单声明，`admin` 动作只有管理员能触发；数据源接口本身要求管理员。
- 驱动拿到的配置由核心合并（钩子级默认值 + 后端行配置 + 运行时 `root`），
  驱动不能决定图片可见性、优先级或过期策略，那些留在 `libs/storage.py`。
