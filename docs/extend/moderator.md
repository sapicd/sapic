# 内容审核（moderator）

审核钩子对**已经入库**的图片给出「通过 / 拦截」结论，属于**先发后审**：上传接口
（`POST /api/v2/upload`）完全不受影响，判定由定时任务扫描完成。慢的外部内容安全 API、
限流与重试都在扫描里消化，不会拖慢用户上传。

```{important}
拦截**只隐藏、不删除**。`block` 只是把图片从公开口径里摘出去（本人与管理员仍可见），
删掉记录是管理员看过之后的明确动作。钩子本身**不允许**改库或删对象。
```

## 声明与必需函数

```python
__catalog__ = "moderator"

def review_image(image, config=None) -> dict:
    ...
```

`moderator` 只有一个必需函数 `review_image`；缺它时钩子清单的 `warnings` 会写
「moderator is missing required function: review_image」，后台钩子页可见。

## 入参：`image`

| 键 | 说明 |
| --- | --- |
| `id` / `sha` | 行 id 与公开标识（`/raw/<sha>`） |
| `filename` / `title` / `mime` / `size` | 元数据 |
| `width` / `height` / `is_video` | 尺寸与是否视频（视频同样送审，由钩子自己决定跳过） |
| `owner_id` / `album_id` / `created_at` | 归属与上传时间；匿名上传的 `owner_id` 为 `null` |
| `src` | 站内路径 `/raw/<sha>` |
| `url` | 绝对地址：优先 `sapic_external_base_url + /raw/<sha>`，否则用登记的外链或公开副本直链（多数内容安全 API 接受图片 URL） |

`config` 是该钩子自己的配置（`hooks_config[<name>]`），字段由 `hook_manifest()` 的
`config_schema` 声明，与其他钩子一致。

> 私有图（单图或继承相册）不会进入审核队列，交给钩子的只有公开可见的图片。
> 三种地址都拿不到时 `url` 仍可能为空，钩子应返回「判不了」让下一轮重试，别猜 `pass`。

## 返回

```python
{"code": 0, "verdict": "block", "message": "nsfw: 0.93"}
```

| 键 | 必需 | 说明 |
| --- | --- | --- |
| `code` | ✅ | `0` 表示本次判定有效；非 0 表示「这次判不了」（超时、配额、服务异常） |
| `verdict` | ✅（`code` 为 0 时） | `pass` 或 `block`，其它值按「判不了」处理 |
| `message` | | 简短原因，写进 `images.review_note`（截断 255），管理员在队列里能看到 |

多个审核钩子并用时的合并规则：

- **任一 `block` 即 block**（一个审核方说有问题就拦）；
- 没有任何 `block`，但存在 `code != 0` 或未知 `verdict` → **不落结论**，下一轮重试；
- 全部有效且都 `pass` 才算 `pass`。

失败时不会猜 `pass`：宁可多扫一轮，也不放行。没给 `message` 时核心会合成一条
（如 `my_moderator: invalid verdict 'approved'`），所以后台队列里很少看不到原因；
定时任务页的「上次结果」也会附上最多 3 条失败样例（`sha: note`），便于定位哪个钩子返回了什么。

## 执行

**默认自动跑**：服务启动后由进程内 APScheduler 每 `SCHEDULER_REVIEW_INTERVAL`（默认 300s）
扫一次，多 worker 用 `data/scheduler.lock` 选主，只有一个进程真正执行，所以不需要 cron。
调度细节见[部署 · 后台任务](../deploy.md)。

手动跑一批（默认 50 张，输出统计）：

```bash
# 在 server/ 下
../.venv/bin/flask sa review-pending -n 50
```

只处理 `status=enabled` 且**尚无结论**的图片，按上传时间从旧到新。每行用一条
`UPDATE ... WHERE review_state IS NULL` 原子抢占，多进程同时跑也不会重复判定
（重复调用意味着重复计费）。判定卡在 `running` 超过 10 分钟（进程被杀）会重新入队。

**判定失败有退避**：钩子判不了的行会退回 `review_state=NULL`，但 `reviewed_at`
保留为本轮时间，1 小时内（`RETRY_DELAY`）不再扫它——否则一个坏钩子会让扫描
每轮都卡在最老的 50 张、后面的图永远轮不到。退避只在**本批**图片太少时会让坏图重新入列；
正常情况下新图先审完，1 小时后再回头重试失败图。

完全不想用内置调度器时（例如已经有了统一的作业系统）：web 端设 `sapic_scheduler=0`，
用 `flask sa scheduler` 或自己的 cron 调 `sa review-pending`：

```text
*/5 * * * * cd /srv/sapic/server && ../.venv/bin/flask sa review-pending -n 50
```

## 结论与管理员处理

`images.review_state`：

| 值 | 含义 |
| --- | --- |
| `NULL` | 未审（含判定失败、退避中待重试；失败原因见 `review_note`） |
| `running` | 某一轮扫描正在处理（短窗口） |
| `pass` | 通过，不再重扫 |
| `block` | 拦截：公开口径（`/raw` 的匿名访问、广场、公开列表）立即不可见 |

管理接口（均需 `admin`，不进 OpenAPI 文档）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v2/review?state=block` | 队列列表，`state` = `block`（默认）/ `pass` / `pending` / `all`，支持 `page` / `page_size` |
| POST | `/api/v2/review/<sha>` | `{"action": "approve", "note": "误判"}` 恢复公开；`{"action": "block"}` 维持拦截；`{"action": "purge"}` **物理删除**（副本与行一起消失，不可恢复） |
| POST | `/api/v2/review/batch` | `{"action": "approve\|block\|purge", "shas": ["..."]}` 批量处理，单次上限 100 张，按 sha 去重；返回 `{"action": ..., "affected": n}` |

`purge` 与过期清理走同一条路径（`libs/images.purge_image`），sha 不会被复用。
后台「审核队列」页（`/admin/review`）把这张队列可视化，支持逐张与批量放行/删除。

站点设置 `review_auto_purge`（默认关）打开后，扫描判定为 `block` 的图片会**立即被 purge**
（副本与行一起删除），不进队列等人复核。这是不可逆操作，误判无法放行挽回，只在能接受
直接删除的部署里开启；默认关闭时 `block` 只隐藏，由管理员在队列里看过再决定。

## 最小实现

```python
# my_moderator.py
__version__ = "0.1.0"
__author__ = "you"
__description__ = "内容安全审核示例"
__catalog__ = "moderator"

import json
from urllib.request import Request, urlopen


def hook_manifest():
    return {
        "title": "内容安全审核",
        "config_schema": [
            {"type": "input", "key": "endpoint", "label": "检测接口", "required": True},
            {"type": "password", "key": "token", "label": "API Token", "required": True},
            {"type": "number", "key": "threshold", "label": "拦截阈值", "default": 0.8},
        ],
    }


def review_image(image, config=None):
    config = config or {}
    if not image.get("url"):
        #: 没有对外地址时判不了，交给下一轮（核心已尝试外链与公开副本直链）。
        return {"code": 1, "message": "image url is not configured"}
    if image.get("is_video"):
        return {"code": 0, "verdict": "pass"}

    body = json.dumps({"url": image["url"]}).encode()
    request = Request(
        config["endpoint"],
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer %s" % config.get("token", ""),
        },
    )
    try:
        with urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode())
    except Exception as exc:  #: 超时/配额/网络问题都算"判不了"
        return {"code": 1, "message": str(exc)}

    score = float(data.get("score") or 0)
    if score >= float(config.get("threshold") or 0.8):
        return {"code": 0, "verdict": "block", "message": "nsfw: %.2f" % score}
    return {"code": 0, "verdict": "pass"}
```

装法与其他钩子一致：放进 `server/data/hooks/`，然后
`POST /api/v2/hooks/import {"module": "my_moderator"}`，再到后台钩子页启用并填配置。

## 注意

- 钩子跑在扫描进程里（`flask sa review-pending`），**不要**假设有请求上下文（没有 `request`、
  没有 `g`）；需要站点地址就读 `image["url"]` 或自己的配置。
- 单张判定要自己设超时；整批的吞吐由 `-n` 与 cron 频率控制，核心不并发调用审核钩子。
- 返回 `block` 之前**不要**自行改库；判定结果由核心统一写入，管理员处理也只走 `/review` 接口。
- 视频默认也会送审（`is_video` 为 `true`）；不想审就按示例直接返回 `pass`。
- `block` 收口的是**本站入口**（`/raw` 的匿名访问、公开列表、广场），不是"内容撤回"：
  默认 `link_mode=raw` 时 `src` 就是 `/raw`，拦截后该地址立即 403；但若切到 `link_mode=direct`，
  公有读桶里那条对象仍可被直接访问，彻底撤回只能由管理员 `purge`（删对象）或调整桶权限。
  要强约束就保持默认模式，或把后端设成 `visibility=private`，所有读取都走 `/raw`。
