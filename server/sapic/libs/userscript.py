# -*- coding: utf-8 -*-
"""sapic.libs.userscript

Render the per-user uploader userscript (Tampermonkey/Violentmonkey).

The generated text carries **no credential**: it asks for an upload-only PAT on
first use and keeps it in the script manager's storage. That way a leaked
install/update URL (which may contain ``?token=``) can never be replayed as an
API token, unlike v1 which embedded the LinkToken in the served source.
"""

from __future__ import annotations

#: Bump when the generated script changes so userscript managers see an update.
#: 1.1.0：安装/更新地址从 /sapic.user.js 移到 /api/v2/userscript.user.js，
#: 老地址已移除，已安装的脚本要按新地址重装一次才能继续收到更新。
USERSCRIPT_VERSION = "1.1.0"

_TEMPLATE = """// ==UserScript==
// @name         Upload to __HOST__
// @namespace    __ROOT__
// @version      __VERSION__
// @description  把网页上的图片上传到 sapic（Alt + 点击图片）；首次使用会要求粘贴只含上传权限的访问令牌。
// @author       sapic
// @match        http://*/*
// @match        https://*/*
// @exclude      __ROOT__*
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_registerMenuCommand
// @grant        GM_xmlhttpRequest
// @connect      __HOST__
// @updateURL    __ROOT__api/v2/userscript.user.js
// @downloadURL  __ROOT__api/v2/userscript.user.js
// @run-at       document-idle
// ==/UserScript==

;(function () {
    'use strict'

    var API = '__ROOT__api/v2/uploads'
    var TOKEN_KEY = 'sapic_token'
    var panel = null

    function token() {
        var saved = GM_getValue(TOKEN_KEY, '')
        if (saved) return saved
        var value = window.prompt('请输入 sapic 访问令牌（只需勾选「上传图片」）：', '')
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
        var colors = {
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
        var credential = token()
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
                var payload = null
                try {
                    payload = JSON.parse(response.responseText)
                } catch (error) {
                    payload = null
                }
                if (response.status !== 201 || !payload || payload.code !== 'OK') {
                    var reason = (payload && payload.message) || ('HTTP ' + response.status)
                    show('上传失败：' + reason, 'error')
                    return
                }
                var link = absolute(payload.data.image.src)
                show('已上传，点击复制：' + link, 'ok', link)
            },
            onerror: function () {
                show('上传失败：网络错误', 'error')
            }
        })
    }

    document.addEventListener(
        'click',
        function (event) {
            if (!event.altKey) return
            var target = event.target
            if (!target || target.tagName !== 'IMG') return
            var src = target.currentSrc || target.src
            if (!src || src.indexOf('data:') === 0) return
            event.preventDefault()
            event.stopPropagation()
            upload(src, target.title || target.alt || '')
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


def build_userscript(root: str, host: str) -> str:
    """Render the script for a site rooted at ``root`` (with trailing slash)."""
    return (
        _TEMPLATE.replace("__ROOT__", root)
        .replace("__HOST__", host)
        .replace("__VERSION__", USERSCRIPT_VERSION)
    )
