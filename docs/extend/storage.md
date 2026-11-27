# 存储驱动（`catalog = "upload"`）

存储驱动只做一件事：**把一段字节写到某个对象存储，并告诉核心它落在哪**。
优先级、多副本、可见性、有效期、删除时机全部由 `sapic/libs/storage.py` 决定，
驱动不要自己维护这些。

## 契约

```python
__catalog__ = "upload"                 # required: otherwise it never shows up in the backend list

def upimg_save(filename, stream, upload_path="", backend=None, **kwargs) -> dict
def upimg_delete(sha, upload_path, filename, basedir, save_result, backend=None) -> dict   # strongly recommended
def upimg_url(save_result, filename="", backend=None, expires=300) -> dict                # required for private buckets
```

| 函数 | 必需 | 说明 |
| --- | --- | --- |
| `upimg_save` | ✅ | 写入对象。`stream` 是 `bytes`（也可能是带 `read()` 的文件对象，两种都要兼容）。 |
| `upimg_delete` | 建议 | 删除一个副本。**不要抛异常**，失败返回 `{"code": 1, "message": ...}`；缺失时副本删不掉，`warnings` 会提示。 |
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

返回值（这是**驱动函数的返回字典**，由 `libs/storage.py` 解析，不是 HTTP 响应体。失败原因统一写
`message`；沿用老字段 `msg` 也还能被识别，但新代码不要再用）：

| 键 | 必需 | 说明 |
| --- | --- | --- |
| `code` | ✅ | `0` 成功；非 0 失败，上传请求随之失败（主后端）或记 `state=failed`（副本） |
| `message` | | 失败原因（英文），写进 `image_backends.last_error` |
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
   `priority` 数值**越小越优先**：写入走数值最小的那行，读取（以及 `link_mode=direct` 下的直链）
  按升序回退。
3. 上传时数值最小的后端同步写，成功后才返回；其余启用后端由后台线程池异步补副本
   （`storage_replica` 关掉就只有单副本）。
4. 删除图片、过期清理都会对每个副本调用 `upimg_delete`；后端仍持有副本时不允许删除该后端。

配置表单字段来自 `hook_manifest()` 的 `config_schema`，`required: true` 没填时后台标
「待配置」、建后端行会 400。驱动可以把「检查连通性」做成 `scope: "admin"` 的 action，
并在 `admin.hook_setting` 插槽里渲染针对单个后端的表单（`context["backend"]` 可读当前后端）。

`config_schema` 里有一个**约定键** `thumb_suffix`：服务层只把它原样拼在公开直链后面
（`libs/storage.thumb_suffix`，裸查询串会自动补 `?`），作为列表页与广场的缩略图，
驱动本身不需要处理。桶或 CDN 支持图片处理时声明它即可，例如七牛
`?imageView2/2/w/400`、又拍 `!/fw/400`；`src` 与分享模板始终是原图，不受影响。

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
| `message` | | 失败原因（英文，只写日志） |
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

## 后台跨后端迁移

管理员在后台「存储」里可对单个后端执行迁移（`POST /api/v2/backends/<id>/migrate`），
把该后端上 `ok` 状态的副本写到目标后端。**默认只复制、不删源站**：源对象与源副本行都保留，
方便先验证目标站；确认无误后回到对话框勾选「迁移完成后删除源站副本」再跑一次，才会清空源站。

- 复制模式：逐条读源字节写入目标，在目标新建副本行（`object_key` 采用目标驱动返回的
  `path`），源副本行原样保留、仍为 `is_primary`；写失败只跳过该图，源不动。
- 删除模式：已有其它健康副本的图直接删源对象与源副本行；唯一副本先写目标成功、
  再删源对象，最后把副本行改挂到目标，全程不会让图片失去最后一个副本。
- 文件名与目录沿用源 `object_key` 的 basename/dirname，但最终 key 由目标驱动的
  `basedir` 规则生成，不同驱动间可能有差异（如又拍 key 带前导 `/`、缤纷云不带）。
- 图片对外链接 `/raw/<sha>` 不变。

内置驱动的实现方式可以直接参照：

| 驱动 | `upimg_url` 做法 |
| --- | --- |
| `up2bitiful` | S3 协议（boto3）：`generate_presigned_url("get_object")` 签发，有效期上限 7 天 |
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
except ImportError:      # optional dependency: do not add it to sapic base.txt
    boto3 = None

__version__ = "0.1.0"
__author__ = "you"
__description__ = "Save to S3-compatible object storage"
__catalog__ = "upload"
__state__ = "disabled"


def hook_manifest():
    return {
        "title": "S3 object storage",
        "catalog": "upload",
        "config_schema": [
            {"type": "input", "key": "endpoint", "label": "Endpoint", "required": True},
            {"type": "input", "key": "bucket", "label": "Bucket", "required": True},
            {"type": "input", "key": "region", "label": "Region"},
            {"type": "input", "key": "access_key", "label": "Access Key", "required": True},
            {"type": "password", "key": "secret_key", "label": "Secret Key", "required": True},
            {"type": "input", "key": "domain", "label": "Public domain",
             "help": "Fill in when a public-read bucket is reachable directly; leave empty for private buckets, served through /raw"},
        ],
        "actions": [{"name": "ping", "label": "Check connectivity", "scope": "admin", "with_form": True}],
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
        return {"code": 1, "message": "Parameter error"}
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
        return {"code": 1, "message": str(exc)}

    result = {"code": 0, "path": key, "size": len(data)}
    domain = str(config.get("domain") or "").strip().rstrip("/")
    if domain:
        #: only public-read buckets get a direct URL; the core ignores it for private backends.
        result["src"] = "%s/%s" % (domain, key)
    return result


def upimg_url(save_result, filename="", backend=None, expires=300, **kwargs):
    """Private bucket: return a short-lived presigned URL that sapic proxies."""
    config = (backend or {}).get("config") or {}
    key = str((save_result or {}).get("path") or "").strip()
    if not key or not config.get("bucket"):
        return {"code": 1, "message": "The object key is required"}
    try:
        url = _client(config).generate_presigned_url(
            "get_object",
            Params={"Bucket": config["bucket"], "Key": key},
            ExpiresIn=int(expires or 300),
        )
    except Exception as exc:
        return {"code": 1, "message": str(exc)}
    return {"code": 0, "url": url}


def upimg_delete(sha, upload_path, filename, basedir, save_result, backend=None, **kwargs):
    config = (backend or {}).get("config") or {}
    key = (save_result or {}).get("path") or _key(upload_path, filename)
    try:
        _client(config).delete_object(Bucket=config["bucket"], Key=key)
    except Exception as exc:
        #: never raise on failure: the core reads code, and raising aborts sibling replica deletes.
        return {"code": 1, "message": str(exc)}
    return {"code": 0}
```

## 注意

- 对象的路径规则、文件名、后缀都由核心生成（`upload_path_for()`），驱动不要另造一套。
- 不要在自己的代码里改图片可见性/过期时间，也不要写业务表；驱动只处理字节。
- 私有图片即使返回了 `src` 也不会直接用，核心固定走 `/raw/<sha>` 转发，
  避免暴露源站地址；返回 `src` 只对公开图片生效。
- `upimg_exists` 是 v1 遗留的探测函数，v2 不调用，可以不实现。
