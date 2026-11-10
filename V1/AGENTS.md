# sapic — 项目上下文

sapic（picbed）是一个基于 Flask 的自建图床，**无 ORM、纯 Redis 存储**，
**存储后端完全插件化（钩子体系）**，当前版本 v1.16.7。

技术栈：Python 3.10+, Flask, Redis, Jinja2, PyJWT, semver, bleach
前端：layui + jQuery + Jinja2 模板
详细架构见 `ARCH.md`，贡献流程见 `CONTRIBUTING.md`。

> Python 版本下限是 **3.10**（`utils.tool.raise_version()` 在应用启动时会强制校验，低于 3.10 直接
> `RuntimeError`）。因此可自由使用 3.10 语法（`X | Y` 联合类型、match 语句、内置泛型 `dict[str]` 等）。
> 注意：历史代码为兼容旧版本而保留的 `_compat` 兼容写法、无注解风格，仍按"精准修改"原则保持不变。

## 目录结构

所有代码以 `src/` 为 Python 模块根（在此目录下运行），不使用包外相对导入：

```
src/
├── app.py        应用入口：Flask 实例、全局钩子、蓝图注册、错误处理
├── config.py     配置：.cfg 文件 → 环境变量 → 默认值（可直接 python config.py 打印）
├── version.py    版本号 __version__
├── sapicd.py     gunicorn 配置（生产部署）
├── views/        路由层  front.py(页面) / api.py(/api/* JSON)
├── libs/         领域核心  storage.py(Redis 单例) / hook.py(插件系统)
├── utils/        基础设施  tool.py(纯工具) / web.py(依赖 Flask 上下文)
│                          / cli.py / _compat.py / exceptions.py / log.py
├── hooks/        内置钩子，一个 .py 即一个插件
├── templates/    public/ control/ layout/ email/ ref/
├── static/       layui/ mymod/ sdk/ share.js/ upload/(up2local 落盘目录)
├── tests/        unittest 测试（test_*.py）
└── Makefile      dev/test/start/stop/reload/restart/status/clean
```

依赖方向单向：`views → libs/utils → utils.tool`。
`utils.tool` 不依赖 Web 框架，`utils.web` 才依赖 `request` / `g` / `current_app`。

## 常用命令

```bash
cd /path/to/sapic/src
make test                     # python -m unittest discover -p "test_*.py"
python config.py              # 打印当前生效配置
flask sa create               # 创建超级管理员
flask sa clean                # 清理数据
flask sa upgrade 1.16         # 版本数据结构迁移（可选 1.6-1.7 / 1.7-1.8 / 1.16）
cd ../docs && make html       # 构建 Sphinx 文档
```

Python 分支：尽量在 dev 分支编码，PR 合并到 dev。

## Python 编码规范

### 基本风格

- 遵循 **PEP 8**，缩进 4 空格，不使用 Tab，文件末尾保留一个空行
- 行宽与既有代码保持一致（约 79 字符）
- 文件头固定写法：`# -*- coding: utf-8 -*-` + 三引号模块 docstring + 版权块

```python
# -*- coding: utf-8 -*-
"""
    utils.xxx
    ~~~~~~~~~

    模块职责一句话描述（英文）。

    :copyright: (c) 2026 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""
```

### 导入顺序

按以下顺序分组，组间空一行：

1. 标准库（`os`, `json`, `time`...）
2. 第三方库（`flask`, `redis`, `semver`...）
3. 项目内部（`views.*` / `libs.*` / `utils.*` / `hooks.*` / `config` / `version`）

风格要点：

- 每个模块单独一行：`import os`、`from os.path import join, exists`
- 同组字母序排列；新模块插到合适位置，不要追加在文件末尾
- 存在循环导入风险时（如 `config`、`utils.web`），允许在函数内延迟导入
- 同一包内可用相对导入（如 `from .storage import get_storage`），跨包一律绝对导入

```python
# 正确示例
import json
from random import choice

from flask import Blueprint, g, request
from redis.exceptions import RedisError

from config import GLOBAL
from utils.tool import rsp, sha1, get_today
from utils.exceptions import ApiError
```

### 命名规范

| 类型 | 风格 | 示例 |
|------|------|------|
| 模块/文件 | snake_case | `up2local.py`, `web.py` |
| 类 | PascalCase | `HookManager`, `JsonResponse` |
| 函数/方法 | snake_case | `get_site_config()`, `upimg_save()` |
| 变量 | snake_case | `upload_path`, `img_url` |
| 常量 | UPPER_SNAKE_CASE | `ALLOWED_EXTS`, `MAX_UPLOAD` |
| 私有成员 | 双下划线 / 单下划线 | `__hooks`, `_compat` |

### 类型注解

- 项目历史代码基本不带注解，**不要大范围补注解**
- 新增函数若需标注，按 3.10+ 写法：`str | None`、`dict[str, Any]`；也可用 `typing` 的
  `Optional`, `Dict`, `List`（`utils/tool.py` 有既有先例）
- 修改已有函数时保持其原有风格（带注解的保持带注解）

```python
def create_redis_engine(redis_url: str | None = None):
    ...
```

### 注释与文档

- **模块级**：文件头三引号，含 `:copyright:` / `:license:` 字段
- **类和函数**：docstring 采用 **Sphinx RST** 格式，用 `:param:`、`:returns:`、`:raises:`
  `` .. versionadded:: `` 等指令
- 模块/函数描述用英文；面向用户的中文说明在 `dfr()` 翻译字典中维护（见下）
- 行内注释用英文，项目惯用 `#:` 开头作为段落级说明注释
- 复杂逻辑注释解释"为什么"，不要复述代码本身

```python
def get_current_timestamp(is_float=False):
    """获取当前时间戳

    :param bool is_float: True则获取10位秒级时间戳，否则原样返回
    """
    return time() if is_float else int(time())
```

### 字符串与格式化

- 项目混用 `%` 与 `.format()`：**改动哪个文件就沿用该文件的既有风格**，不在同一文件内混用两种方式
- 拼接路径用 `os.path.join` / `posixpath.join`，不要手拼 `/`

### 异常处理

- 自定义异常：`ApiError`（返回 JSON）、`PageError`（返回 `public/error.html`），均继承 `PicbedError`
- 签名：`ApiError(message, code=-1, status_code=200)`
- 视图函数可直接 `res = dict(code=1, msg=...)` 返回，也可 `raise ApiError(...)`
- 禁止裸 `except:`，至少 `except Exception:` 或明确异常元组
- Redis / HTTP / 第三方 SDK 调用需捕获特定异常并转换为 `ApiError` 或带 `msg` 的失败响应
- 不用 `print()` 打日志，统一用 `utils.tool` 的 `logger` / `err_logger`

### API 错误规范（含国际化）★

面向用户的消息统一 **英文原文 + `dfr()` 中文翻译**：

- `raise ApiError("No valid backend storage service")` 中的 message 必须是英文
- 新增英文文案必须同步在 `utils/web.py` 的 `dfr()` → `trans["zh-CN"]` 字典中登记中文，
  否则中文用户只能看到英文（代码会 `logger.debug("Miss translation: %s")`)
- 不要在视图里返回中文 `msg`，这会绕过翻译体系
- 保持第三方客户端兼容：`/api/upload` 的 `format` / `status_name` / `ok_code` / `msg_name`
  参数行为不可变更（PicGo / uPic 依赖）

### Redis 数据操作

两类存储边界要分清：

- **系统级键值**：走 `libs/storage.py` 的 `RedisStorage`（`get_storage()`），数据 JSON 序列化后
  统一放 `picbed:dat` hash（`siteconfig` / `hookloadtime` / `hookthirds` / `hookstate`）
- **业务数据**：走 `utils.web` 的模块级 `rc`，key 统一由 `utils.tool.rsp()` 生成
  （自带 `picbed:` 前缀，如 `rsp("image", sha)` → `picbed:image:{sha}`）
- 新增 key 必须遵循上述前缀规则，并在 `ARCH.md` 的 key 表中补充说明
- 批量查询用 `pipeline` + `hmget`，禁止在循环里单条 `hgetall`
- 兼容 Redis 3.x：`hmset` 已统一替换为 `hset`，新增代码同样使用 `hset`
- 数据结构变更无法通过 ORM 迁移，需要在 `utils/cli.py` 的 `upgrade` 命令中手写 Redis 迁移脚本

## 钩子（插件）开发规范

`hooks/*.py` 一个文件即一个钩子，新增钩子必须满足：

```python
# -*- coding: utf-8 -*-
"""
    hooks.up2xxx
    ~~~~~~~~~~~~

    One-line description in English.

    :copyright: (c) 2026 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

__version__ = "0.1.0"
__author__ = "your name"
__description__ = "中文功能描述"
__catalog__ = "upload"      # 归类，upload 表示存储后端
__state__ = "disabled"      # enabled / disabled
__hookname__ = "Up2Xxx"     # 可选，友好名
__appversion__ = "1.16.7"   # 可选，第三方钩子需与当前版本 semver 匹配
```

要点：

- 必备元数据 `__version__` 与 `__author__`，第三方额外要求 semver 合法、`__appversion__` 匹配
- **无 import 副作用的模块级代码**：钩子会被反复重新加载，不要在模块顶层初始化连接
- `upimg_save(**kwargs)` 统一返回 `dict(code=0, src=...)` 或 `dict(code=1, msg=...)`
- `upimg_delete(sha, upload_path, filename, basedir, save_result)` 清理远端文件，失败不外抛
- 第三方 SDK 依赖：
  - 依赖写到 `requirements/xxx.txt`，代码里 `try: import xxx except ImportError:` 并给出
    英文提示 `Please install xxx module`（同时登记 `dfr()` 翻译）
  - 不要在 `requirements/base.txt` 强制引入可选 SDK
- 钩子自带的 `templates/` 挂进 Jinja `ChoiceLoader`，`static/` 走 `/assets/<hook_name>/<filename>`

## 前端规范 (JavaScript / Jinja2)

### JavaScript

- **变量定义必须使用 `let`**，禁止使用 `var`；常量用 `const`
- 注意：存量模板/静态 js 中仍有大量 `var`，**不要顺手全局替换**，只保证新增代码用 `let/const`
- 使用 `===` / `!==` 而不是 `==` / `!=`
- 函数名 camelCase；避免在全局作用域污染，包在 IIFE 或 `layui.use()` 回调内
- 不在 HTML 属性里写内联 JS（`onclick="..."`），统一 jQuery 事件绑定
- 不写 `console.log` 调试日志
- jQuery 对象变量加 `$` 前缀：`let $tip = $('#tip');`
- 渲染用户输入用 `.text()`，确需 HTML 时先做转义防 XSS

```javascript
// 正确
layui.use(['jquery'], function () {
    let $box = $('#sessions-box');
});

// 错误
var $box = $('#sessions-box');
```

### Jinja2 模板

- 模板后缀 `.html`（**不是 `.j2`**），注释用 `{# 注释 #}`
- URL 一律用 `url_for()`，不硬编码路径
- 模板全局变量由框架注入：
  - `Version` / `is_true` / `timestamp_to_timestring` / `get_page_msg` / `get_push_msg`（`app.py`）
  - `intpl` / `get_call_list` / `emit_assets` / `es`（钩子模板片段与静态资源注入）
- 页面消息：管理员用 `set_page_msg` / `get_page_msg`，用户用 `push_user_msg` / `get_push_msg`

## 文档与变更记录

- 用户文档在 `docs/`，**Sphinx + reStructuredText**，后缀 `.rst`，内容为中文
- **每次新增功能、修复问题或行为变更，必须同时更新三处**：
  1. `docs/changelog.rst`（顶部新增版本条目）
  2. `src/version.py` 的 `__version__`
  3. 若涉及数据结构变更，`src/utils/cli.py` 的 `upgrade` 迁移脚本

`docs/changelog.rst` 格式（版本号 + 分隔线 + 发布日期 + 精简条目）：

```rst
v1.16.8
--------

Released in 2026-9-22

- 新增：某某钩子支持 XXX。
- 修复：某某场景下 YYY 的问题。
```

要求：

- 条目精简概括，**禁止堆砌实现细节、文件路径、Redis key、函数名**
- 例外：用户可直接感知的入口（如 CLI 命令、配置项）可写明
- 涉及配置项的变更同步更新 `docs/conf.rst` 的配置表与 `ARCH.md`

## 持续集成 / 质量

- 测试：`make test`（unittest，`python -m unittest discover -p "test_*.py"`，须在 `src/` 下执行，Python 3.10+）
- 无 pytest 依赖，新测试写在 `src/tests/test_xxx.py`
- 提交前保证导入可用、应用能启动（`flask sa` 命令可正常加载）
- 建议同步更新 `ARCH.md` 中的目录/key 表/扩展点清单描述

## 已知技术债（改动时注意，详见 ARCH.md 第十节）

- `upimg_save` 当前只取第一条结果，多后端聚合尚未实现
- `POST /api/extendpoint?Object=&Action=` 无鉴权反射调用钩子方法，慎改
- 上传限流用 `scard` 读后判断，并发存在竞态
- 钩子热重载依赖 Redis 中按 pid 存储的时间戳，多进程需 gunicorn 钩子清理

## 编码前思考
- 明确假设，不确定时询问而非猜测。
- 存在歧义时，列出多种解释，不默默选定单一方案。
- 如果任务有明显更简单的做法，直接指出优化思路。
- 发现代码矛盾、逻辑不一致时及时暂停，请求信息澄清。

## 简洁优先
- 用最少的代码解决问题，拒绝冗余实现。
- 不为一次性需求创建抽象层、复杂架构。
- 不盲目增加扩展性、可配置性，应对“未来可能用到”的场景。
- 若代码可大幅精简，主动重写优化。
- 校验标准：以资深工程师视角判断，代码若过于复杂，立即简化。

## 精准修改
- 仅修改与当前任务直接相关的代码内容。
- 不顺手优化相邻代码、注释、排版格式。
- 不重构原本可以正常运行的代码模块。
- 严格匹配项目现有代码风格，保留原有编码习惯。
- 因本次修改产生的无效导入、废弃变量，可直接删除。
- 发现项目中原有的死代码、冗余内容，仅做文字提醒，不擅自删除。

## 目标驱动执行
- 执行任务前，定义清晰、可落地的成功标准。
- 将“修复Bug”转化为：编写用例复现问题，再调试至用例正常通过。
- 将“新增校验功能”转化为：针对异常输入编写测试用例，保证全部通过。
- 将“代码重构”转化为：完成重构后，确保原有所有测试用例正常运行。
- 多步骤复杂任务，先输出简短执行计划，同时标注每一步的验证方式。
