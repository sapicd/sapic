// ==UserScript==
// @name        Upload to picbed <{{ request.host }}@{{ g.userinfo.username }}>
// @version     0.2.1
// @description 上传图片到picbed
// @author      staugur
// @namespace   https://www.saintic.com/
// @include     http://*
// @include     https://*
// @exclude     {{ request.url_root }}*
// @exclude     https://*.aliyun.com/*
// @grant       GM_info
// @created     2020-05-27
// @modified    2020-08-18
// @github      https://github.com/staugur/picbed
// @supportURL  https://github.com/staugur/picbed/issues/
// @updateURL   {{ url_for('front.userscript', LinkToken=g.userinfo.ucfg_userscript_token, _external=True) }}
// @icon        {{ g.site.favicon or url_for('static', filename='img/favicon.png', _external=True) }}
// ==/UserScript==

(function () {
    'use strict';

    const cfg = {
        "hot_key": "{{ g.userinfo.ucfg_userscript_hotkey or 'ctrlKey' }}",
        "api_url": "{{ url_for('api.upload', _external=True) }}",
        "link_token": "{{ g.userinfo.ucfg_userscript_token }}",
        "upload_name": "{{ g.site.upload_field or 'picbed' }}",
        "id": "picbed-menu",
    };

    let isObject = v => Object.prototype.toString.call(v) === '[object Object]',
        hasMenu = () => document.getElementById(cfg.id) ? true : false,
        getMenu = () => document.getElementById(cfg.id),
        hasSendingMenu = () => {
            if (hasMenu()) {
                let p = getMenu();
                if (p && p.dataset.sendStatus === "sending") {
                    return true;
                }
            }
            return false;
        },
        setBtnText = text => {
            if (text) getMenu().querySelector("button").textContent = text;
        },
        removeMenu = () => {
            if (hasMenu()) getMenu().remove();
        };

    function upload(e, opts) {
        let src = e.target.src;
        if (!src) return false;
        if (!opts) opts = {};
        if (!isObject(opts)) return false;

        let data = new FormData();
        data.append(cfg.upload_name, src);
        data.append('title', e.target.title || e.target.alt || '');
        data.append('origin', `userscript/${GM_info.script.version}`);
        Object.assign(opts, {
            url: cfg.api_url,
            method: "POST",
            headers: {
                Authorization: `LinkToken ${cfg.link_token}`
            },
            data: data,
        });

        let xhr = new XMLHttpRequest(),
            error = typeof opts.error === 'function' ? opts.error : msg => {
                console.error(msg);
            };
        xhr.responseType = 'json';
        xhr.open(opts.method, opts.url, true);
        for (let key in opts.headers) {
            xhr.setRequestHeader(key, opts.headers[key]);
        }
        xhr.onloadstart = opts.start || null;
        xhr.onload = function () {
            typeof opts.success === 'function' && opts.success(xhr.response);
        };
        xhr.onerror = error("请求错误");
        try {
            xhr.send(opts.data);
        } catch (e) {
            error("网络异常");
        };
    }

    function createMenu(e, onClick) {
        if (hasSendingMenu()) return false;
        removeMenu();

        let src = e.target.src;
        let wrapperCss = [
            "position: absolute",
            `left: ${e.pageX}px`,
            `top:${e.pageY}px`,
            "z-index: 9999999",
            "width: 200px",
            "background-color: #fff",
            "color: #000",
            "text-align: center",
            "border: 1px #409eff solid",
            "font-size: 14px",
            "line-height: 24px",
            "overflow: hidden",
            "white-space: nowrap",
            `text-overflow: ".../${src.split("/").slice(-1)[0]}"`,
        ];
        let wrapper = document.createElement('div');
        wrapper.style.cssText = wrapperCss.join(";");
        wrapper.textContent = src;
        wrapper.setAttribute('id', cfg.id);

        let btnCss = [
            'display: block',
            'margin: 0 auto',
            'width: 100%',
            'padding: 5px 10px',
            'font-size: 12px',
            'background-color: #fff',
            'color: #409eff',
            'border: 0px',
            'cursor: pointer',
            'user-select: none',
        ];
        let btn = document.createElement('button');
        btn.style.cssText = btnCss.join(";");
        btn.textContent = "点击上传";
        btn.onclick = onClick;

        wrapper.appendChild(btn);
        document.body.appendChild(wrapper);
    }

    document.addEventListener('mousedown', function (e) {
        //恢复默认右键菜单
        document.oncontextmenu = null;
        //在图片上使用 快捷键+鼠标右击 打开自定义菜单
        if (e[cfg.hot_key] === true && e.button === 2) {
            if (e.target.tagName.toLowerCase() === 'img' && e.target.src) {
                //确定选中图片右键，打开上传菜单
                document.oncontextmenu = () => false;
                createMenu(e, () => {
                    let menu = getMenu();
                    menu.querySelector("button").onclick = null;
                    menu.querySelector("button").style.cursor = 'text';
                    if (/^(?:blob:|filesystem:)/.test(e.target.src)) {
                        setBtnText("不支持的图片格式");
                        return false;
                    }
                    if (location.protocol === "https:" && cfg.api_url.split("://")[0] === "http") {
                        setBtnText("禁止混合内容");
                        return false;
                    }
                    upload(e, {
                        start: () => {
                            menu.dataset.sendStatus = "sending";
                            setBtnText("正在上传...");
                        },
                        success: res => {
                            if (res.code === 0) {
                                menu.dataset.sendStatus = "success";
                                setBtnText("上传成功");
                            } else {
                                menu.dataset.sendStatus = "fail";
                                setBtnText(res.msg);
                            }
                        },
                        error: msg => {
                            menu.dataset.sendStatus = "error";
                            setBtnText(msg);
                        },
                    });
                });
            }
        } else {
            //非面板内的点击/右击等操作（且无发送中状态）则关闭菜单
            if (e.target.id !== cfg.id && e.target.parentElement && e.target.parentElement.id !== cfg.id) {
                if (!hasSendingMenu()) removeMenu();
            }
        }
    }, true);
})();