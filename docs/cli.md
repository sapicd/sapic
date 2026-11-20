# 命令行工具 sapicli

`sapicli` 是独立的 Go 程序（仓库 [sapicd/cli](https://github.com/sapicd/cli)），不依赖 Python
环境，官方发布 Windows / macOS / Linux 三端压缩包（amd64 与 arm64），解压即用，功能覆盖上传、
相册、有效期、输出风格与剪贴板复制。

```{note}
`sapicli` 是**独立项目**，从 **v0.6.0**（2026-11）起**同时支持 v1 与 v2 接口**：`-u` 只填站点
根地址（接口路径自动拼接），`-t` 在 v2 站点上换成 PAT（`sp_` 开头）。参数、输出风格与剪贴板行为
在 v1 / v2 下完全一致，接口版本默认自动判定，也可以用 `-A` 指定。更早的版本只认 v1 接口。
```

## 功能

- 批量上传任意数量图片（并发上传），支持匿名上传与临时图片（有效期）
- 设置相册、标题/描述
- 多种输出风格：`default`、`typora`、`line`、`empty` 与自定义模块
- 上传结果跨平台复制到剪贴板，支持 URL / Markdown / rST 三种格式

## v1 与 v2

| 项目 | v1 站点 | v2 站点（本仓库当前版本） |
| --- | --- | --- |
| 上传接口 | `POST /api/upload` | `POST /api/v2/upload` |
| 认证头 | `Authorization: LinkToken <token>` | `Authorization: Bearer <PAT>` |
| 请求体 | 表单，图片 base64 放在 `picbed` 字段 | `multipart/form-data`，文件放在 `file` 字段 |
| 相册 | `album`（相册名） | `album_id`（`-a` 传名称时工具先解析成 id） |

- `-u` 只写**站点根地址**（如 `https://your.site`），`/api/upload` 或 `/api/v2/upload` 由工具
  自动拼接；写成 `https://your.site/api/v2` 也可以，工具会把路径剥掉再补。
- v2 的令牌是 **PAT**：站点「设置 → 访问令牌」里创建，勾选 `upload` 作用域，形如 `sp_...`。
  `-a` 传**相册名**时工具要先 `GET /api/v2/albums` 解析 id，令牌需要同时带 `read`（默认创建就含）；
  直接传**相册 id** 则只要 `upload`。相册名解析失败只会打一行日志并退回令牌默认相册，不会中断上传。
- v2 的响应信封（`code` / `message` / `data`）会被展平成 v1 的结果结构，`-s` 与 `-c` 的表现
  不变；失败时 `message` 里会附上 `request_id`，排查问题时可凭它在服务端日志里定位。

**接口版本自动判定顺序**（`-A auto`，默认）：

1. 显式指定的 `-A`；
2. `-u` 里已经带了 `/api/v2` 或 `/api/upload`；
3. 探测 `GET /api/v2/site`（5 秒超时），`data.version` 以 `2.` 开头即 v2；
4. 令牌以 `sp_` 开头；
5. 都不满足就回退 v1。

站点探测不到（内网、离线、域名不可达）时用 `-A v2` 明确指定最省事。

## 安装

到 [cli release](https://github.com/sapicd/cli/releases) 下载对应压缩包：Windows 选
`xxx-windows-amd64.zip`（ARM 机器选 `arm64`），macOS Intel 选 `xxx-darwin-amd64.tar.gz`、
Apple Silicon 选 `xxx-darwin-arm64.tar.gz`。压缩包里只有一个可执行文件，放进 `PATH` 里的目录，
或直接用绝对路径调用。

macOS 也可以用 Homebrew 安装：

```bash
brew tap staugur/tap
brew install sapicli
```

需要容器里用时，官方镜像 `staugur/sapicli` 也可直接用：

```bash
docker run --rm -ti staugur/sapicli -h
```

## 命令选项

```text
$ sapicli -h
usage: sapicli [-h] [-v] [-i] [-u SAPIC_URL] [-t SAPIC_TOKEN] [-a ALBUM] [-d DESC] [-e EXPIRE] [-s STYLE] [-c {url,md,rst}] [-A {auto,v1,v2}] file [file ...]

Doc to https://sapic.readthedocs.io/zh-cn/latest/cli.html
Git to https://github.com/sapicd/cli

positional arguments:
  file                  local image file

optional arguments:
  -h, --help            show this help message and exit
  -v, --version         show cli version and exit
  -i, --info            show full info and exit
  -u, --sapic-url SAPIC_URL
                        The sapic site url, the api path is appended
                        automatically. Or use environment variable:
                        sapicli_apiurl
  -t, --sapic-token SAPI_TOKEN
                        The sapic token: a LinkToken for v1, a PAT(sp_...) for
                        v2. Or use environment variable: sapicli_apitoken
  -a, --album ALBUM     Set image album, its name or its id(v2 only)
  -d, --desc DESC       Set image title(description)
  -e, --expire EXPIRE   Set image expire(seconds)
  -s, --style STYLE     The upload output style: { default, typora, line,
                        empty, }. allows to pass in a python module name, and
                        use "python -m py-mod-name" to customize the output
                        style.
  -c, --copy {url,md,rst}
                        Copy the uploaded image url type to the clipboard for
                        Windows/macOS/Linux. By the way, md=Markdown,
                        rst=reStructuredText
  -A, --api-version {auto,v1,v2}
                        The sapic api version to talk to, auto detects it from
                        the site and the token. v1 = POST /api/upload with
                        "Authorization: LinkToken ", v2 = POST /api/v2/upload
                        with "Authorization: Bearer ".
```

| 选项 | 说明 |
| --- | --- |
| `-u` | 站点根地址，可省略 `http://`，接口路径自动补齐（v1 / v2 自适应）；也可用环境变量 `sapicli_apiurl` |
| `-t` | 令牌：v1 用 LinkToken，v2 用 PAT（`sp_` 开头，需 `upload`）；也可用环境变量 `sapicli_apitoken` |
| `-a` | 相册，可覆盖令牌默认相册；v2 支持相册名或相册 id |
| `-d` | 图片标题（描述） |
| `-e` | 有效期（秒），用于临时图片 |
| `-s` | 输出风格，见下 |
| `-c` | 上传后按 `url` / `md` / `rst` 复制到剪贴板 |
| `-A` | 接口版本：`auto`（默认）/ `v1` / `v2` |
| `-i` | 打印 CLI 与接口版本、commit、Go 版本、平台等完整信息后退出 |

**输出风格**：

| 风格 | 行为 |
| --- | --- |
| `default` | 打印完整的 JSON 上传结果（含失败项） |
| `typora` | 专给 Typora 的格式，只输出成功上传的图片地址 |
| `line` | 与 `typora` 类似，但不打印提示文字，每行一个地址 |
| `empty` | 不输出内容 |
| `<模块名>` | 自定义输出：sapicli 用 `python -m <模块名>` 调用它，result 以 JSON 从位置参数传入 |

自定义输出的模块示例：

```python
# output.py -- invoked with `sapicli ... -s output`
from sys import argv
from json import loads

if __name__ == "__main__":
    for item in loads(argv[1]):
        print("py mod diy:", item["src"])
```

**剪贴板复制**：`-c url` 复制裸地址，`-c md` 复制 `![1.png](http://cdn.com/1.png)`，
`-c rst` 复制 reST 的 `.. image::` 形式；多个文件的结果用换行连接。Windows 用 `clip`，
macOS 用 `pbcopy`，Linux 需要先装 `xclip`（仅桌面环境）。

```{tip}
上传的文件要放在**所有选项之后**，否则选项会被当成文件名。
```

## 示例

```bash
# v2 站点：-u 只给站点根地址，-t 用 PAT
sapicli -u https://your.site -t sp_xxxxxxxx -a album-name -d "screenshot" a.png b.png

# 站点探测不到时显式指定 v2，-a 也可以直接给相册 id
sapicli -u https://your.site -t sp_xxxxxxxx -A v2 -a 12 a.png

# 上传后把 Markdown 链接复制到剪贴板
sapicli -u https://your.site -t sp_xxxxxxxx -c md screenshot.png

# 临时图片：2 小时后过期
sapicli -u https://your.site -t sp_xxxxxxxx -e 7200 temp.png

# v1 老站点：把 -t 换回 LinkToken 即可，其余参数不变
sapicli -u https://old.site -t <LinkToken> a.png
```

## 作为 Typora 上传服务

Typora → **偏好设置 → 图像**：插入图片时选「上传图片」，上传服务选 **Custom Command**，
命令填：

```text
sapicli -u https://your.site -t sp_xxxxxxxx -s typora "$@"
```

点「验证图片上传选项」确认可用。不想依赖 CLI 时，也可以用[快捷上传](usage.md)里的
`curl` 脚本，效果一致。

## 右键菜单

Windows 与 macOS 的右键上传菜单（含 sapicli 与免安装的 `.cmd` 脚本两种方式）统一整理在
[快捷上传](usage.md)的「Windows 右键菜单」「macOS 右键菜单」两节，这里不再重复。
