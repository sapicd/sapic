# 命令行工具 sapicli

`sapicli` 是独立的 Go 程序（仓库 [sapicd/cli](https://github.com/sapicd/cli)），不依赖 Python
环境，官方发布 Windows / macOS / Linux 三端压缩包，解压即用，功能覆盖上传、相册、有效期、
输出风格与剪贴板复制。

```{note}
CLI 目前仍按 v1 接口设计：`-u` 指向站点地址后会自动补 `/api/upload`，`-t` 传的是 v1 的 LinkToken。
**支持 v2 的版本发布后，只需把 `-u` 指向站点根地址、`-t` 换成 PAT**，命令行参数与输出风格保持不变。
在那之前，v2 站点请先用[快捷上传](usage.md)里的 curl / PicGo 方案。
```

## 功能

- 批量上传任意数量图片，支持匿名上传与临时图片（有效期）
- 设置相册、标题/描述
- 多种输出风格：`default`、`typora`、`line`、`empty` 与自定义模块
- 上传结果跨平台复制到剪贴板，支持 URL / Markdown / rST 三种格式

## 安装

到 [cli release](https://github.com/sapicd/cli/releases) 下载对应压缩包：Windows 选
`xxx-windows-amd64.zip`，macOS 选 `xxx-darwin-amd64.tar.gz`。压缩包里只有一个可执行文件，
放进 `PATH` 里的目录，或直接用绝对路径调用。

macOS 也可以用 Homebrew 安装：

```bash
brew tap staugur/tap
brew install sapicli
```

## 命令选项

```text
$ sapicli -h
usage: sapicli [-h] [-v] [-i] [-u SAPIC_URL] [-t SAPIC_TOKEN] [-a ALBUM]
                  [-d DESC] [-e EXPIRE] [-s STYLE] [-c {url,md,rst}]
                  file [file ...]

Doc to https://sapic.rtfd.vip/zh-cn/latest/cli.html
Git to https://github.com/sapicd/cli

positional arguments:
  file                  local image file

optional arguments:
  -h, --help            show this help message and exit
  -v, --version         show cli version and exit
  -i, --info            show full info and exit
  -u, --sapic-url SAPIC_URL
                        The sapic upload api url.
  -t, --sapic-token SAPIC_TOKEN
                        The sapic token.
  -a, --album ALBUM     Set image album
  -d, --desc DESC       Set image title(description)
  -e, --expire EXPIRE   Set image expire(seconds)
  -s, --style STYLE     The upload output style: {default, typora, line, empty, <MOD>}
  -c, --copy {url,md,rst}
                        Copy the uploaded image url type to the clipboard
```

| 选项 | 说明 |
| --- | --- |
| `-u` | 站点地址，可省略 `http://`，末尾的接口路径也会自动补齐；也可用环境变量 `sapicli_apiurl` |
| `-t` | 访问令牌，需要上传权限；也可用环境变量 `sapicli_apitoken` |
| `-a` | 相册名，可覆盖令牌默认相册 |
| `-d` | 图片标题（描述） |
| `-e` | 有效期（秒），用于临时图片 |
| `-s` | 输出风格，见下 |
| `-c` | 上传后按 `url` / `md` / `rst` 复制到剪贴板 |

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
# output.py —— 用 `sapicli ... -s output` 调用
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
# 上传两张图片，设置相册与描述
sapicli -u https://your.site -t <Token> -a 相册名 -d "截图" a.png b.png

# 上传后把 Markdown 链接复制到剪贴板
sapicli -u https://your.site -t <Token> -c md screenshot.png

# 临时图片：2 小时后过期
sapicli -u https://your.site -t <Token> -e 7200 temp.png
```

## 作为 Typora 上传服务

Typora → **偏好设置 → 图像**：插入图片时选「上传图片」，上传服务选 **Custom Command**，
命令填：

```text
sapicli -u https://your.site -t <Token> -s typora "$@"
```

点「验证图片上传选项」确认可用。不想依赖 CLI 时，也可以用[快捷上传](usage.md)里的
`curl` 脚本，效果一致。

## Windows 右键菜单

用 [OpenWithPlusPlus](https://github.com/stax76/OpenWithPlusPlus)：安装后 **add** 一条菜单项：

| 项 | 值 |
| --- | --- |
| Name | `Upload to sapic` |
| File Type | `%image%` |
| Path | `sapicli.exe` 的绝对路径 |
| Arguments | `-u https://your.site -t <Token> -c md "$@"` |
| 其他 | 勾选 **Run hidden** |

## macOS 右键菜单

用系统自带的「自动操作」（Automator）新建 **快速操作**：「工作流程收到当前」选**图像文件**、
位于**访达**，拖入 **运行 Shell 脚本**，传递输入选**作为自变量**，脚本内容：

```bash
sapicli -u https://your.site -t <Token> -c md "$@"
```

保存在「快速操作」里之后，访达中右键图片即可上传，Markdown 链接会进剪贴板。
