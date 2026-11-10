# 快捷上传

网页之外，sapic 还能被桌面工具、编辑器直接调用。所有方式走的都是同一个上传接口，
区别只在「谁发起请求」。先准备一个令牌：

1. 登录站点，进入 **设置 → 访问令牌**，点「新建令牌」；
2. 作用域只勾 **上传图片**（`upload`）即可，客户端不需要读、写或管理权限；
3. 令牌只在创建时显示一次（形如 `sp_xxxxxxxx`），下面统一写作 `<PAT>`。

```{note}
浏览器的登录会话不能直接当 API 令牌用：会话请求必须带 CSRF 头，客户端带不了。
这也是为什么所有客户端都要求配置 PAT。
```

## 接口

上传只有一个端点：`POST /api/v2/upload`，请求体是 `multipart/form-data`：

| 字段 | 说明 |
| --- | --- |
| `file` | 文件域，与 `url` 二选一 |
| `url` | 图片地址，由服务端抓取后入库（直连抓不到时可在后台「站点设置 → 上传 → 下载代理」配 `http(s)` 代理兜底） |
| `album_id` | 可选，相册 ID（需登录，且对该相册有写权限） |
| `title` | 可选，标题 |
| `expire` | 可选，有效期（秒）；留空用站点默认值，`0` 表示永久 |

鉴权用请求头 `Authorization: Bearer <PAT>`，成功返回 **HTTP 201**。

所有 `/api/v2` 接口共用同一层包装（下称「信封」）：`{code, message, data}` ——
成功时 `code` 恒为 `"OK"`；失败时它是错误枚举（`UNAUTHORIZED` / `FORBIDDEN` / `PARAM_ERROR` …）
且 `data` 为 `null`。上传的图片对象在 `data.image` 里，地址取 `data.image.src`：

```bash
curl -X POST "https://your.site/api/v2/upload" \
  -H "Authorization: Bearer sp_xxxxxxxx" \
  -F "file=@/path/to/image.png" \
  -F "title=海边"
```

```json
{
  "code": "OK",
  "message": "",
  "data": {
    "image": {
      "sha": "....",
      "filename": "image.png",
      "src": "https://your.site/raw/...."
    }
  }
}
```

失败同样是 v2 信封，只是 `code` 变成错误枚举并带对应状态码：

| 状态码 | `code` | 常见原因 |
| --- | --- | --- |
| 400 | `PARAM_ERROR` | 既没有 `file` 也没有 `url`，或 `album_id` 不是数字 |
| 401 | `UNAUTHORIZED` | 令牌无效、被撤销或已过期 |
| 403 | `FORBIDDEN` | 令牌缺 `upload` 权限、站点关闭匿名上传、账号未通过审核 |
| 404 | `NOT_FOUND` | `album_id` 不存在或不属于你 |
| 413 | `PARAM_ERROR` | 文件超过上限 |

## PicGo

1. 安装 [PicGo](https://github.com/Molunerfinn/PicGo/releases)；
2. 在 **插件设置** 里搜索并安装 `web-uploader`；
3. 打开 **图床设置 → 自定义 Web 图床**，按下表填写，然后把它设为默认图床：

| 项 | 值 |
| --- | --- |
| `url` | `https://your.site/api/v2/upload` |
| `paramName` | `file` |
| `jsonPath` | `data.image.src` |
| `customHeader` | `{"Authorization": "Bearer sp_xxxxxxxx"}` |
| `customBody` | `{"title": "从 PicGo 上传"}`（可选） |

`customHeader` 是必需的；`customBody` 只用来附加可选字段（标题、有效期）。

## PicGo-Core（命令行）

PicGo 桌面版的底层就是 PicGo-Core，很多编辑器插件也调用它。只想要命令行上传时：

```bash
npm install -g picgo
picgo install web-uploader
```

把配置写进 `~/.picgo/config.json`（`picgo set uploader web-uploader` 也可以，但逐项输入比较慢）：

```json
{
  "picBed": {
    "current": "web-uploader",
    "uploader": "web-uploader",
    "web-uploader": {
      "url": "https://your.site/api/v2/upload",
      "paramName": "file",
      "jsonPath": "data.image.src",
      "customHeader": "{\"Authorization\": \"Bearer sp_xxxxxxxx\"}",
      "customBody": "{\"title\": \"\"}"
    }
  }
}
```

`customHeader` 与 `customBody` 的值是**字符串化的 JSON**，注意转义。之后：

```bash
picgo upload ./image.png     # 输出图片地址
picgo upload                 # 不带参数则上传剪贴板里的图片
```

```{tip}
只是偶尔在命令行传几张图的话，用 [sapicli](cli.md) 更省事：不用装 Node、不用写配置文件，
`-u` / `-t` 直接给地址和令牌，`-c md` 还能顺手把链接放进剪贴板。
```

## uTools

uTools 应用市场里的「图床」插件多数基于 PicGo 内核，能安装 `web-uploader` 的话，
配置项与前面 PicGo 一节完全相同。插件只提供「自定义接口」表单时，按下面的对应关系填：

| 插件里的字段 | 值 |
| --- | --- |
| 上传地址 / URL | `https://your.site/api/v2/upload` |
| 文件字段名 | `file` |
| 请求头 | `Authorization: Bearer sp_xxxxxxxx` |
| 返回字段 / JSON 路径 | `data.image.src` |

如果这一版的插件两者都不支持，用 uTools 的「快捷命令」直接跑下文的脚本，
把关键字设成 `upload`，参数选「文件/图片」。

## uPic（macOS）

[uPic](https://github.com/gee1k/uPic) 是 macOS 上常用的菜单栏图床工具，添加一个「自定义」图床：

| 项 | 值 |
| --- | --- |
| API 地址 | `https://your.site/api/v2/upload` |
| 请求方式 | `POST` |
| 文件字段名 | `file` |
| URL 路径 | `["data", "image", "src"]` |
| 请求头 | `Authorization` = `Bearer sp_xxxxxxxx` |

## ShareX（Windows）

ShareX 适合「截图 → 自动上传 → 链接进剪贴板」的流程。在 **目标 → 上传目标 → 自定义上传目标**
新建一项：

| 项 | 值 |
| --- | --- |
| 请求 URL | `https://your.site/api/v2/upload` |
| 请求方法 | `POST` |
| 请求体 | `Form (multipart/form-data)` |
| File form name | `file`（值类型选 **File**） |
| 附加参数 | `title`（可选） |
| 请求头 | `Authorization: Bearer sp_xxxxxxxx` |
| 响应解析 | JSON 路径 `$.data.image.src` |

响应是上面那层统一包装，`src` 藏在 `data.image.src`。老版本 ShareX 只支持正则时，
用 `"src"\s*:\s*"([^"]+)"` 也能取到——JSON 里只有 `data.image.src` 这一处 `src` 键
（`tpl.HTML` 里的地址是 `src='...'`，单引号，不会被这条正则命中）。

## 编辑器插件（VS Code / Obsidian）

这类插件多数只是调用 PicGo 或 PicGo-Core，**图床配置沿用上文即可**，插件里只需要指到可执行文件：

- VS Code：安装 PicGo 相关扩展（如 `PicGo`、`Markdown Image`），设置里填 `picgo` 的路径；
  保存/粘贴图片时自动上传并插入 Markdown。
- Obsidian：安装 `Image auto upload` 插件，上传器选 PicGo 或 PicGo-Core，
  同样读取 `~/.picgo/config.json`。

## Typora

Typora 的上传服务有三种接法，任选其一：

1. **PicGo**：上传服务选 **PicGo**，填 `picgo` 的可执行文件路径，图床配置见上面 PicGo 一节。
2. **sapicli**：上传服务选 **Custom Command**，命令填
   `sapicli -u https://your.site -t <PAT> -s typora "$@"` —— `-s typora` 的输出正好是
   Typora 要的格式；需要 CLI 支持 v2 的版本，用法见[命令行工具](cli.md)。
3. **自带脚本**：见下，不用装任何工具，只要一条能把文件传上去并输出 URL 的命令。

方式三的脚本存成 `/usr/local/bin/sapic-upload` 并 `chmod +x`（Windows 用后面
「Windows 右键菜单」里的 `.cmd`）：

```sh
#!/bin/sh
# 上传一个文件并输出图片地址；Typora 会读取 stdout 的第一行作为图片链接。
SAPIC="https://your.site"
TOKEN="sp_xxxxxxxx"

curl -sS -X POST "$SAPIC/api/v2/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@$1" \
  | /usr/bin/python3 -c 'import json,sys; print((json.load(sys.stdin).get("data") or {}).get("image", {}).get("src", ""))'
```

然后在 Typora **偏好设置 → 图像**：插入图片时选「上传图片」，上传服务选 **Custom Command**，
命令填 `/usr/local/bin/sapic-upload "$@"`（或用上面第 2 种的 `sapicli ...`），
点「验证图片上传选项」确认可用。

```{tip}
需要在正文里插入 Markdown 而不是裸链接时，把最后一行换成输出
`![](url)` 的写法即可；Typora 只要求每次上传输出一行文本。

脚本用 `python3` 解析 JSON（macOS 由 Xcode 命令行工具提供）。机器上没有 `python3`
时，改用 `jq`：把管道末尾换成 `| jq -r '.data.image.src // empty'`，记得先 `brew install jq`。
```

## Windows 右键菜单

两种方式二选一，都用 [OpenWithPlusPlus](https://github.com/stax76/OpenWithPlusPlus) 挂到右键菜单：
装了 sapicli 走方式一，没装走方式二（需要 Windows 10 及以上自带的 `curl.exe`）。

### 方式一：sapicli

安装后 **add** 一条菜单项：

| 项 | 值 |
| --- | --- |
| Name | `Upload to sapic` |
| File Type | `%image%` |
| Path | `sapicli.exe` 的绝对路径 |
| Arguments | `-u https://your.site -t <PAT> -c md "$@"` |
| 其他 | 勾选 **Run hidden** |

`-c md` 复制 Markdown 链接（`-c url` 复制裸地址、`-c rst` 复制 reST），
sapicli 需要支持 v2 的版本，见[命令行工具](cli.md)。

### 方式二：自带 .cmd 脚本

同样在 OpenWithPlusPlus 里 **add**，Path 指向 `C:\tools\sapic-upload.cmd`（下面这个脚本），
Arguments 填 `"%1"`，勾选 **Run hidden**：

```bat
@echo off
setlocal
set "SAPIC=https://your.site"
set "TOKEN=sp_xxxxxxxx"

curl -sS -X POST "%SAPIC%/api/v2/upload" ^
  -H "Authorization: Bearer %TOKEN%" ^
  -F "file=@%~f1" > "%TEMP%\sapic-upload.json"

for /f "delims=" %%i in ('powershell -NoProfile -Command ^
  "(Get-Content -Raw '%TEMP%\sapic-upload.json' | ConvertFrom-Json).data.image.src"') do set "URL=%%i"

rem 复制到剪贴板，右键点完直接可粘贴
echo %URL% | clip
```

上传成功后图片地址已经进了剪贴板；想改成上传完自动打开图片，把最后一行换成
`start "" "%URL%"`。

## macOS 右键菜单

用系统自带的「自动操作」（Automator）做「快速操作」，脚本二选一：

- 「工作流程收到当前」选 **图像文件**，「位于」选 **访达**；
- 从资源库拖入 **运行 Shell 脚本**，「传递输入」选 **作为自变量**，Shell 选 `/bin/sh`；
- 脚本内容二选一（`/bin/sh` 下都可用）：

**方式一**，装了 sapicli（一行就够，`-c md` 把 Markdown 链接放进剪贴板）：

```sh
sapicli -u https://your.site -t <PAT> -c md "$@"
```

**方式二**，不装工具，用 curl + python3：

```sh
SAPIC="https://your.site"
TOKEN="sp_xxxxxxxx"

for f in "$@"; do
  curl -sS -X POST "$SAPIC/api/v2/upload" \
    -H "Authorization: Bearer $TOKEN" \
    -F "file=@$f" \
    | /usr/bin/python3 -c 'import json,sys; print((json.load(sys.stdin).get("data") or {}).get("image", {}).get("src", ""))'
done | pbcopy
```

保存为 `Upload to sapic`。之后在访达里选中图片 → 右键 → **快速操作** 即可，
地址会写进剪贴板。

## 油猴脚本

浏览器里 Alt（或 Ctrl）+ 点击任意网站的图片就能直接上传。先在 **设置 → 个性化** 打开
「油猴脚本」开关，用同一行右侧的安装地址装到 Tampermonkey，首次上传时粘贴一个只含
`upload` 的 PAT 即可（脚本源码里不含任何令牌，令牌存在脚本管理器本地）。

- Windows：`Ctrl + 点击` 或 `Alt + 点击`
- macOS：`Alt + 点击`（`Ctrl + 点击` 是系统右键，脚本也做了兼容）

## 常见问题

| 现象 | 原因与处理 |
| --- | --- |
| `{"code":"FORBIDDEN","message":"anonymous upload is disabled"}` | 没带令牌，或站点关闭了匿名上传；按上文配置 PAT |
| `{"code":"UNAUTHORIZED","message":"invalid token"}` | 令牌填错或已撤销，重新建一个 |
| `token scope does not allow upload` | 令牌没勾「上传图片」，重新建一个 |
| `invalid csrf token` | 用浏览器会话直接调接口了，客户端请改用 PAT |
| 413 / `file exceeds N MB` | nginx 的 `client_max_body_size`、`sapic_maxupload`、后台单文件上限三者取最小值 |
| `file type is not allowed` | 后台「上传后缀白名单」没放开该格式 |
| 上传成功但链接打不开 | 图片在私有相册 / 私有后端，只有登录后经 `/raw/<sha>` 才能访问 |
| 客户端报「找不到图片地址」 | JSON 路径填错：v2 信封是 `data.image.src`，不是 `src` |
