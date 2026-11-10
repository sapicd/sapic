# -*- coding: utf-8 -*-
"""sapic.libs.userscript

Render the per-user uploader userscript (Tampermonkey/Violentmonkey).

The generated text carries **no credential**: it asks for an upload-only PAT on
first use and keeps it in the script manager's storage. That way a leaked
install/update URL (which may contain ``?token=``) can never be replayed as an
API token, unlike v1 which embedded the LinkToken in the served source.
"""

from __future__ import annotations

from urllib.parse import urlsplit

#: Bump when the generated script changes so userscript managers see an update.
#: 1.1.0：安装/更新地址从 /sapic.user.js 移到 /api/v2/userscript.user.js，
#: 老地址已移除，已安装的脚本要按新地址重装一次才能继续收到更新。
#: 1.2.0：脚本内部只用 const / let，不再出现 var。
#: 1.3.0：``@name`` 沿用 v1 的 ``Upload to sapic <host@username>``，多站点并存时能分辨。
#: 1.4.0：Ctrl 与 Alt 都能触发上传，Windows / macOS 各自用习惯的键。
#: 1.5.0：``@connect`` 同时给带端口与不带端口的主机名，修「domain 不在 @connect 列表」。
#: 1.6.0：上传地址跟随接口改名（``/api/v2/upload``），旧版脚本升级后才能继续上传。
USERSCRIPT_VERSION = "1.6.0"

_TEMPLATE = """// ==UserScript==
// @name         Upload to sapic <__HOST__@__USERNAME__>
// @namespace    __ROOT__
// @version      __VERSION__
// @description  把网页上的图片上传到 sapic（Alt / Ctrl + 点击图片）；首次使用会要求粘贴只含上传权限的访问令牌。
// @author       sapic
// @match        http://*/*
// @match        https://*/*
// @exclude      __ROOT__*
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_registerMenuCommand
// @grant        GM_xmlhttpRequest
// @connect      __CONNECT__
// @updateURL    __ROOT__api/v2/userscript.user.js
// @downloadURL  __ROOT__api/v2/userscript.user.js
// @run-at       document-idle
// ==/UserScript==

;(function () {
    'use strict'

    const API = '__ROOT__api/v2/upload'
    const TOKEN_KEY = 'sapic_token'
    let panel = null

    function token() {
        const saved = GM_getValue(TOKEN_KEY, '')
        if (saved) return saved
        let value = window.prompt('请输入 sapic 访问令牌（只需勾选「上传图片」）：', '')
        value = (value || '').trim()
        if (value) GM_setValue(TOKEN_KEY, value)
        return value
    }

    function absolute(src) {
        if (!src) return ''
        if (src.indexOf('://') > 0) return src
        return '__ROOT__' + src.replace(/^\\//, '')
    }

    function show(text, state, copyText) {
        if (!panel) {
            panel = document.createElement('div')
            panel.style.cssText =
                'position:fixed;right:16px;bottom:16px;z-index:2147483647;' +
                'max-width:360px;padding:10px 12px;border-radius:8px;' +
                'font:13px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;' +
                'color:#fff;box-shadow:0 6px 20px rgba(0,0,0,.25);word-break:break-all;'
            document.body.appendChild(panel)
        }
        const colors = {
            pending: 'rgba(37,99,235,.95)',
            ok: 'rgba(22,163,74,.95)',
            error: 'rgba(220,38,38,.95)'
        }
        panel.style.background = colors[state] || colors.pending
        panel.textContent = text
        panel.title = copyText ? '点击复制链接' : ''
        panel.onclick = function () {
            if (!copyText || !navigator.clipboard) return
            navigator.clipboard.writeText(copyText)
        }
        clearTimeout(panel._timer)
        panel._timer = setTimeout(function () {
            if (panel) {
                panel.remove()
                panel = null
            }
        }, state === 'ok' ? 12000 : 6000)
    }

    function upload(src, title) {
        const credential = token()
        if (!credential) {
            show('未设置访问令牌，已取消上传', 'error')
            return
        }
        show('上传中…', 'pending')
        GM_xmlhttpRequest({
            method: 'POST',
            url: API,
            headers: {
                Authorization: 'Bearer ' + credential,
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            data:
                'url=' + encodeURIComponent(src) +
                '&title=' + encodeURIComponent(title || ''),
            onload: function (response) {
                let payload = null
                try {
                    payload = JSON.parse(response.responseText)
                } catch (error) {
                    payload = null
                }
                if (response.status !== 201 || !payload || payload.code !== 'OK') {
                    const reason = (payload && payload.message) || ('HTTP ' + response.status)
                    show('上传失败：' + reason, 'error')
                    return
                }
                const link = absolute(payload.data.image.src)
                show('已上传，点击复制：' + link, 'ok', link)
            },
            onerror: function () {
                show('上传失败：网络错误', 'error')
            }
        })
    }

    //: 只接管「Ctrl 或 Alt + 点击图片」：Windows 习惯 Ctrl，macOS 习惯 Alt。
    function pickImage(event) {
        if (!event.altKey && !event.ctrlKey) return null
        const target = event.target
        if (!target || target.tagName !== 'IMG') return null
        const src = target.currentSrc || target.src
        if (!src || src.indexOf('data:') === 0) return null
        return { src: src, title: target.title || target.alt || '' }
    }

    function onClick(event) {
        const image = pickImage(event)
        if (!image) return
        event.preventDefault()
        event.stopPropagation()
        upload(image.src, image.title)
    }

    document.addEventListener('click', onClick, true)
    //: macOS 的 Ctrl + 左键派发的是 contextmenu 而不是 click，补一条兜底。
    document.addEventListener(
        'contextmenu',
        function (event) {
            if (!event.ctrlKey) return
            onClick(event)
        },
        true
    )

    GM_registerMenuCommand('设置 sapic 访问令牌', function () {
        GM_setValue(TOKEN_KEY, '')
        token()
    })
    GM_registerMenuCommand('清除 sapic 访问令牌', function () {
        GM_setValue(TOKEN_KEY, '')
        show('已清除本地访问令牌', 'ok')
    })
})()
"""


def connect_hosts(host: str) -> list[str]:
    """``@connect`` values for ``host``: the exact one plus a port-less twin.

    Tampermonkey matches ``host:port`` fine, but managers that compare by
    hostname only (ScriptCat, some Violentmonkey versions) reject a request to
    ``127.0.0.1:5173`` unless ``127.0.0.1`` is listed separately. Emitting both
    keeps the dev server and the production host working.
    """
    hosts = [host]
    bare = urlsplit("//%s" % host).hostname or ""
    if bare and ":" in bare:
        bare = "[%s]" % bare
    if bare and bare != host:
        hosts.append(bare)
    return hosts


def build_userscript(root: str, host: str, username: str) -> str:
    """Render the script for a site rooted at ``root`` (with trailing slash).

    ``@name`` keeps the v1 shape (``Upload to sapic <host@username>``) so the
    manager's list tells apart installs pointing at different sites/accounts.
    The username is substituted last: it is already restricted to
    ``[a-z0-9_]`` by ``validate_username`` and must not be re-scanned for other
    placeholders.
    """
    return (
        _TEMPLATE.replace("__ROOT__", root)
        .replace("__HOST__", host)
        .replace("__CONNECT__", "\n// @connect      ".join(connect_hosts(host)))
        .replace("__VERSION__", USERSCRIPT_VERSION)
        .replace("__USERNAME__", username)
    )
