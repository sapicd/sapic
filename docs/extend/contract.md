# 钩子基础契约

任何钩子（不管是不是扩展点）都遵循这一套元数据与清单契约。

## 模块元数据

```python
__version__ = "1.0.0"          # 必需：缺失则该模块被跳过
__author__ = "your-name"       # 必需
__description__ = "一句话说明"
__catalog__ = "upload"         # auth / upload / processor，留空视为纯界面钩子
__state__ = "enabled"          # 首次加载的默认状态，disabled 表示默认关闭
```

`__hookname__`、`__appversion__` 也可选，会原样出现在 `GET /api/v2/hooks` 的元数据里。

`__catalog__` 决定**扩展类型**，只有三个值有专门契约：`auth`（登录 Provider）、`upload`（存储驱动）、
`processor`（字节流后处理）；其他值或留空都按纯界面钩子处理（清单里的 `kind` 为 `ui`）。
声明的类型与模块实际导出的函数对不上时，`warnings` 里会列出缺失的函数名。

## 清单：`hook_manifest()`

一个可调用对象，返回如下字典（全部可选，核心会补齐默认值并清洗）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `title` | str | 展示名，缺省用模块名 |
| `catalog` | str | 展示分组，缺省取 `__catalog__`。**一般不要写**：前端靠 `catalog === "upload"` 判断「这是存储驱动，凭据在存储后端页配置」，覆盖成别的值会让钩子页露出重复的配置表单 |
| `description` | str | 说明，缺省取 `__description__` |
| `config_schema` | list | 配置表单字段（下表） |
| `actions` | list | 可触发动作：`{name, label, scope, with_form, confirm}` |
| `data_sources` | list | 只读数据集：`{name, label}` |
| `slots` | list | 声明界面插槽：`[{name: "nav"}]`，渲染模式固定 `declarative` |

核心会额外输出 `kind`、`warnings`、`enabled`、`family`、`version`、`author`、`ui_version`。

### `config_schema` 字段

| 键 | 说明 |
| --- | --- |
| `type` | `input` / `number` / `password` / `textarea` / `switch` / `select` / `radio` |
| `key` | 配置键，保存进 `hooks_config[<hook>][<key>]` |
| `label` | 表单标签 |
| `default` | 默认值 |
| `required` | 必填（存储驱动的必填项会影响「是否可用」判定） |
| `help` / `placeholder` | 提示文案 |
| `format` | 提示前端用哪种控件，如 `path` |
| `options` | `select` / `radio` 的选项：`[{label, value}]` |
| `multiple` | `select` 是否多选 |

只有清单声明的键才能写库，未知键一律 400。

### 函数命名规则

| 清单声明 | 钩子需要实现 | 调用时传入 |
| --- | --- | --- |
| `slots: [{name: "nav"}]` | `slot_nav(context, values)` | `context`（含本钩子 `config`）、`values` |
| `actions: [{name: "ping"}]` | `action_ping(payload, context, values)` | 同上，`payload` 是请求体 |
| `data_sources: [{name: "items"}]` | `data_items(query, context)` | `query` 是查询串字典 |

点号会被换成下划线：插槽 `admin.hook_setting` → `slot_admin_hook_setting`。
函数签名只写需要的参数即可（核心按签名过滤关键字参数），`**kwargs` 会收到全部。

## 插槽白名单

`nav`、`login.after_form`、`profile`、`user.setting`、`admin.site_setting`、
`admin.hook_setting`、`image.detail`、`upload.after`。

不在白名单里的插槽会被丢弃。以 `admin.` 开头的插槽、`scope: "admin"` 的动作与
数据源接口只对管理员开放。

## 界面节点词表

钩子返回节点树（`{type, ...}` 或它们的列表），前端只有一个递归渲染器，
所有类型与键都在 `libs/ui.py` 里白名单化：

- **结构**：`fieldset`、`group`、`row`（`gap`）、`col`（`span`）、`tabs`、`collapse`、
  `list`（`empty`）、`list_item`（`title`、`description`、`row_actions`）
- **展示**：`text`（`muted`）、`alert` / `badge`（`level`）、`image`（`src`、`alt`、`fit`）、
  `code`、`divider`（`label`）
- **表单**：`input`、`number`、`password`、`textarea`、`switch`、`select`、`radio`
  （键与 `config_schema` 基本一致）
- **交互**：`button`（`action`、`with_form`、`confirm`、`refresh`、`variant`、`size`）、
  `link`（`href`、`target`）、`dropdown` / `dropdown_item`

约定与限制：

- 每个节点都可带 `when: {field, op, value}`，按当前表单值决定是否渲染（`eq` / `ne` 等）。
- 文案里的 `{key}` 会用 `context` 的值替换，用于显示 `{username}` 之类的信息。
- `href` 只接受站内路径或 `http(s)` 协议，`//evil.com` 会被丢弃。
- `action` 必须是清单里声明过的名字，否则按钮不生效。
- 图标写 `builtin:xxx` 或 `brand:xxx`。前端是一张**固定映射表**
  （`web/src/components/hook/icons.js`），当前可用的 `builtin` 只有：`plug`、`external`、`link`、
  `refresh`、`settings`、`upload`、`download`、`copy`、`tool`、`star`、`delete`；
  `brand:*` 不论叫什么一律显示通用链接图标。
  表里没有的 `builtin:xxx` **不报错也不显示**（`<el-icon>` 直接不渲染）；不带前缀的名字在清洗阶段
  就被丢弃。
- 单次返回节点数、层级、文本长度都有上限（`MAX_CHILDREN` / `MAX_DEPTH` / `MAX_TEXT`）。

## 动作与数据集返回值

这里有**三层**「响应」，键名相近但互不相同，先分清再写代码：

| 层 | 形状 | 由谁产出 | 谁消费 |
| --- | --- | --- | --- |
| HTTP 信封 | `{code: "OK" \| 错误枚举, message, data}` | `views/*` 的 `ok()` / 异常处理器 | 前端 `api/client.js`、外部客户端 |
| 钩子动作 / 数据集 | `{code: 0 \| 非0, message, toast, refresh}`、`{items, total}` | 你的 `action_*` / `data_*` | 核心**原样塞进** HTTP 信封的 `data` |
| 存储驱动 | `{code: 0 \| 非0, message, path / url / size}` | 你的 `upimg_*` | `libs/storage.py`，**不会**直接出现在 HTTP 响应里 |

所以动作接口的真实响应是两层嵌套：

```json
{
  "code": "OK",
  "message": "",
  "data": {
    "code": 0,
    "message": "",
    "toast": { "level": "success", "text": "已保存" },
    "refresh": true
  }
}
```

- 外层 `code` 是传输层结果，HTTP 200 时恒为 `"OK"`；内层 `code` 才是你的业务结果，`0` 成功、非 0 失败；
- 失败原因写在 `message`（英文），由前端映射成中文；`refresh: true` 让前端刷新当前块；
- 数据集返回 `{items: [...], total: n}`，单行只保留可序列化的标量字段；
- 驱动 / processor / provider 的返回值同样是 `code: int` + `message`；沿用了老字段 `msg` 的
  第三方驱动仍能工作（核心按 `message or msg` 读取），但新代码不要再用，见[存储驱动](storage.md)。

## 相关接口

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/v2/hooks` | 登录 | 清单列表 + 当前用户可见的插槽名 |
| GET | `/api/v2/hooks/manifests` | admin | 全部清单（含未启用） |
| POST | `/api/v2/hooks/reload` | admin | 立即重载 |
| PATCH | `/api/v2/hooks/<name>` | admin | `{enabled: bool}`，持久化到 `hooks_state` |
| GET | `/api/v2/hooks/slots/<slot>` | 匿名 | 渲染插槽，`?context=` 传 JSON |
| POST | `/api/v2/hooks/<name>/actions/<action>` | 登录 | 触发动作（`admin` scope 需管理员） |
| GET | `/api/v2/hooks/<name>/data/<source>` | admin | 读数据集 |
| GET/PUT | `/api/v2/hooks/config[/<name>]` | admin | 读写钩子配置 |
| POST | `/api/v2/hooks/import` | admin | 登记模块名（第三方钩子入口） |
| GET | `/api/v2/hooks/packages` | admin | 已安装包与包目录 |
| POST | `/api/v2/hooks/install` | admin | `pip install` 到包目录 |
| GET | `/api/v2/hooks/market` | admin | 市场列表（`page` / `page_size` 分页）+ 本地安装/加载状态 |
