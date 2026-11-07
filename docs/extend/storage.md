# 存储驱动（`catalog = "upload"`）

存储驱动只做一件事：**把一段字节写到某个对象存储，并告诉核心它落在哪**。
优先级、多副本、可见性、有效期、删除时机全部由 `sapic/libs/storage.py` 决定，
驱动不要自己维护这些。

## 契约

```python
__catalog__ = "upload"                 # 必需：否则不会出现在后端列表里

def upimg_save(filename, stream, upload_path="", backend=None, **kwargs) -> dict
def upimg_delete(sha, upload_path, filename, basedir, save_result, backend=None) -> dict   # 强烈建议
def upimg_url(save_result, filename="", backend=None, expires=300) -> dict                # 私有桶必需
```

| 函数 | 必需 | 说明 |
| --- | --- | --- |
| `upimg_save` | ✅ | 写入对象。`stream` 是 `bytes`（也可能是带 `read()` 的文件对象，两种都要兼容）。 |
| `upimg_delete` | 建议 | 删除一个副本。**不要抛异常**，失败返回 `{"code": 1, "msg": ...}`；缺失时副本删不掉，`warnings` 会提示。 |
| `upimg_url` | 私有桶必需 | 签发临时读地址，见下文「私有桶」。只在后端 `visibility=private` 时被调用。 |

`upimg_save` 的参数：

| 参数 | 说明 |
| --- | --- |
| `filename` | 已清洗的目标文件名（含后缀，可能带 sha 片段），由核心生成 |
| `stream` | 文件内容 |
| `upload_path` | 对象前缀（`{用户}/{Y}/{m}/{d}`），与 `filename` 拼成对象键 |
| `backend` | 该次调用使用的后端配置：`{id, name, hook_name, config, visibility, priority}` |

`backend["config"]` 是合并结果：钩子级默认值 → 后端行的 `config` → 运行时补充
（本地驱动会补 `root = STORAGE_DIR`）。所以同一个驱动可以被配置成多个后端实例，
每个实例有独立凭据/目录。

返回值：

| 键 | 必需 | 说明 |
| --- | --- | --- |
| `code` | ✅ | `0` 成功；非 0 失败，上传请求随之失败（主后端）或记 `state=failed`（副本） |
| `msg` | | 失败原因（英文），写进 `image_backends.last_error` |
| `path` | ✅ | 对象键，删除时用它定位 |
| `src` | | 可直接访问的绝对地址。只在桶**公有读**且配了域名时返回；省略（或不配域名）就由 sapic 的 `/raw/<sha>` 输出。私有桶不要返回它 |
| `size` | | 字节数，缺省用上传长度的值 |
| `etag` | | 存储侧校验值/版本号，删除时可用于精确定位 |

`upimg_delete` 的参数：`sha`、`upload_path`、`filename`、`basedir`
（配置里的 `root`，远程驱动一般忽略）、`save_result`
（`{path, size, etag}`，来自保存时的返回值）、`backend`。返回 `{"code": 0}` 表示已删除。

## 生效方式

1. 在后台启用钩子（`PATCH /api/v2/hooks/<name>`）后，`sync_backends()` 会自动创建一条
   `scope=system` 的后端行，所以「启用驱动」就是唯一的必要动作。
2. 后台「存储后端」页可以再建多个实例（不同桶/目录）、调整优先级、单独配置、启停。
   优先级数字**越小越先**：写入走第一个，读取按顺序回退。
3. 上传时主后端同步写，成功后才返回；其余启用后端由后台线程池异步补副本
   （`storage_replica` 关掉就只有单副本）。
4. 删除图片、过期清理都会对每个副本调用 `upimg_delete`；后端仍持有副本时不允许删除该后端。

配置表单字段来自 `hook_manifest()` 的 `config_schema`，`required: true` 没填时后台标
「待配置」、建后端行会 400。驱动可以把「检查连通性」做成 `scope: "admin"` 的 action，
并在 `admin.hook_setting` 插槽里渲染针对单个后端的表单（`context["backend"]` 可读当前后端）。

## 私有桶

后端行的 `visibility` 决定 sapic 怎么读对象：

| 取值 | 桶的读权限 | 公开图的 `src` | `/raw/<sha>` 的读法 |
| --- | --- | --- | --- |
| `public`（默认） | 公有读（+ CDN 域名） | 直接给驱动返回的直链 | 本地 `send_file`；远程 302（公开图）或转发（私有图） |
| `private` | **私有读**，匿名请求 403 | 固定 `/raw/<sha>` | 本地 `send_file`；远程先调 `upimg_url` 拿临时地址，再由 sapic 转发 |

`private` 的完整流程：

1. `image_src()` 只认 `public` 后端的直链，`private` 后端即使驱动返回了 `src` 也不用；
2. 浏览器请求 `/raw/<sha>`，sapic 先做可见性 / 防盗链校验；
3. 找到该副本，调驱动的 `upimg_url(save_result, backend, expires)`；
4. 驱动返回临时读地址（有效期由驱动决定，默认建议 300 秒）；
5. sapic 在服务端拉取并流式转发（**不 302**），签名地址与凭据都不会到浏览器；
6. 某个副本失败就换下一个副本，而不是直接 404。

`upimg_url` 的返回值：

| 键 | 必需 | 说明 |
| --- | --- | --- |
| `code` | ✅ | `0` 成功；非 0 视为该副本不可读（会尝试下一个） |
| `msg` | | 失败原因（英文，只写日志） |
| `url` | ✅ | 临时可读地址；可以是 CDN 地址、签名 URL，或对象存储的 REST 源站地址 |
| `headers` | | 转发时必须追加的请求头。不能把凭据放进 URL 的存储（又拍的 `Authorization` + `Date`）靠它 |

守卫与限制：

- 后端选 `private` 但驱动没实现 `upimg_url`，建/改后端直接 400
  （`driver cannot read private objects: missing upimg_url`），后台「访问方式」里的该选项也会置灰。
- `up2local` 例外：本地副本由 `send_file` 直接读盘，不需要 `upimg_url`，可以设 `private`。
- `visibility` 默认 `public`；本次升级前的存量后端行由迁移 `v011` 一次性回填为 `public`，行为不变。
- 转发目标是服务端产生的地址，因此 `/raw` 调用 `open_remote(..., allow_private=True)`：自建 MinIO
  在 `10.x`/`192.168.x` 也能读。用户提交的 URL（URL 上传、外链登记）仍然走公网校验，二者不可混用。
- 私有桶会**失去 CDN 直链**：公开图也要过 sapic，按需给公开图单独建一个 `public` 后端并调高优先级。

内置驱动的实现方式可以直接参照：

| 驱动 | `upimg_url` 做法 |
| --- | --- |
| `up2qiniu` | `Auth.private_download_url(domain + "/" + key, expires)`；私有桶仍需配 `domain` |
| `up2upyun` | 无预签名 URL：指向 `https://v0.api.upyun.com/{bucket}/{key}`，返回 `Authorization: UPYUN op:base64(hmac-sha1(md5(pwd), "GET&uri&date"))` + `Date` |
| `up2github` | 私有仓库走 contents API（`Accept: application/vnd.github.raw`），返回 `Authorization: token ...` |
| `up2local` | 不需要：`/raw` 直接读盘 |
| 通用对象存储 | S3/OSS/COS/MinIO 都用 SDK 的 presigned URL（见下面示例的 `upimg_url`） |

## 示例

```python
# sapic_storage_s3/__init__.py
try:
    import boto3
except ImportError:      # 可选依赖：不要写进 sapic 的 base 依赖
    boto3 = None

__version__ = "0.1.0"
__author__ = "you"
__description__ = "保存到 S3 兼容对象存储"
__catalog__ = "upload"
__state__ = "disabled"


def hook_manifest():
    return {
        "title": "S3 对象存储",
        "catalog": "upload",
        "config_schema": [
            {"type": "input", "key": "endpoint", "label": "Endpoint", "required": True},
            {"type": "input", "key": "bucket", "label": "Bucket", "required": True},
            {"type": "input", "key": "region", "label": "Region"},
            {"type": "input", "key": "access_key", "label": "Access Key", "required": True},
            {"type": "password", "key": "secret_key", "label": "Secret Key", "required": True},
            {"type": "input", "key": "domain", "label": "访问域名",
             "help": "公有读桶可直接访问时填；私有桶留空，由 sapic 的 /raw 转发"},
        ],
        "actions": [{"name": "ping", "label": "检查连通性", "scope": "admin", "with_form": True}],
        "slots": [{"name": "admin.hook_setting"}],
    }


def _client(config):
    if boto3 is None:
        raise ValueError("Please install boto3 module")
    return boto3.client(
        "s3",
        endpoint_url=config.get("endpoint") or None,
        region_name=config.get("region") or None,
        aws_access_key_id=config.get("access_key") or None,
        aws_secret_access_key=config.get("secret_key") or None,
    )


def _key(upload_path, filename):
    return "/".join(part.strip("/") for part in (upload_path, filename) if part)


def upimg_save(filename, stream, upload_path="", backend=None, **kwargs):
    config = (backend or {}).get("config") or {}
    if not filename or not config.get("bucket"):
        return {"code": 1, "msg": "Parameter error"}
    data = stream if isinstance(stream, (bytes, bytearray)) else stream.read()
    key = _key(upload_path, filename)
    try:
        _client(config).put_object(
            Bucket=config["bucket"],
            Key=key,
            Body=data,
            ContentType=kwargs.get("mime") or "application/octet-stream",
        )
    except Exception as exc:
        return {"code": 1, "msg": str(exc)}

    result = {"code": 0, "path": key, "size": len(data)}
    domain = str(config.get("domain") or "").strip().rstrip("/")
    if domain:
        #: 只有公有读桶才给直链；后端设成 private 时核心也不会用它。
        result["src"] = "%s/%s" % (domain, key)
    return result


def upimg_url(save_result, filename="", backend=None, expires=300, **kwargs):
    """私有桶：签发一个短期可读的预签名地址，由 sapic 服务端转发。"""
    config = (backend or {}).get("config") or {}
    key = str((save_result or {}).get("path") or "").strip()
    if not key or not config.get("bucket"):
        return {"code": 1, "msg": "The object key is required"}
    try:
        url = _client(config).generate_presigned_url(
            "get_object",
            Params={"Bucket": config["bucket"], "Key": key},
            ExpiresIn=int(expires or 300),
        )
    except Exception as exc:
        return {"code": 1, "msg": str(exc)}
    return {"code": 0, "url": url}


def upimg_delete(sha, upload_path, filename, basedir, save_result, backend=None, **kwargs):
    config = (backend or {}).get("config") or {}
    key = (save_result or {}).get("path") or _key(upload_path, filename)
    try:
        _client(config).delete_object(Bucket=config["bucket"], Key=key)
    except Exception as exc:
        #: 失败不要抛：核心按 code 判定，抛出会打断同批次的其它副本删除。
        return {"code": 1, "msg": str(exc)}
    return {"code": 0}
```

## 注意

- 对象的路径规则、文件名、后缀都由核心生成（`upload_path_for()`），驱动不要另造一套。
- 不要在自己的代码里改图片可见性/过期时间，也不要写业务表；驱动只处理字节。
- 私有图片即使返回了 `src` 也不会直接用，核心固定走 `/raw/<sha>` 转发，
  避免暴露源站地址；返回 `src` 只对公开图片生效。
- `upimg_exists` 是 v1 遗留的探测函数，v2 不调用，可以不实现。
