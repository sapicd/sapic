// ==UserScript==
// @name        Upload to picbed <{{ request.host }}@{{ g.userinfo.username }}>
// @version     0.1.4
// @description 上传图片到picbed
// @author      staugur
// @namespace   https://www.saintic.com/
// @include     http://*
// @include     https://*
// @exclude     {{ request.url_root }}*
// @exclude     https://*.aliyun.com/*
// @run-at      document-start
// @grant       GM_getValue
// @grant       GM_info
// @created     2020-05-27
// @modified    2020-07-03
// @github      https://github.com/staugur/picbed
// @supportURL  https://github.com/staugur/picbed/issues/
// @updateURL   {{ url_for('front.userscript', LinkToken=g.userinfo.ucfg_userscript_token, _external=True) }}
// @icon        {{ g.site.favicon or url_for('static', filename='img/favicon.png', _external=True) }}
// ==/UserScript==

'use strict';

var setting = {
    "hot_key": "{{ g.userinfo.ucfg_userscript_hotkey or 'ctrlKey' }}",
    "server_url": "{{ url_for('api.upload', _external=True) }}",
    "link_token": "{{ g.userinfo.ucfg_userscript_token }}",
    "upload_name": "{{ g.site.upload_field or 'picbed' }}",
};
var opt_panel = null;
var disable_contextmenu = false;
var img_src = null;
var last_update = 0;
var xhr = new XMLHttpRequest();
var reader = new FileReader();
reader.onload = function (file) {
    upload_file(this.result);
};

var i18n = {
    'zh': {
        'ca': '确认终止上传文件吗？',
        'us': '上传完成！',
        'uf': '上传失败！',
        'utp': '上传到picbed',
        'iu': '正在上传...',
    },
    'en': {
        'ca': 'Are you sure to cancel uploading?',
        'us': 'Upload finished!',
        'uf': 'Upload failed!',
        'utp': 'Upload to picbed',
        'iu': 'Uploading...',
    }
};
var lang = (navigator.language || navigator.browserLanguage).split('-')[0];
if (!i18n[lang]) lang = 'en';

function create_panel() {
    //图片右键弹出的"上下文"菜单
    opt_panel = document.createElement('div');
    opt_panel.style.cssText = 'width: 180px; font-size: 14px; text-align: center; position: absolute; color: #000; z-index: 9999999999; box-shadow: 2px 2px 3px rgba(0, 0, 0, 0.5); border: 1px solid #CCC; background: rgba(255, 255, 255, 0.9); border-top-right-radius: 2px; border-bottom-left-radius: 2px; font-family: "Arial"; -webkit-user-select: none; -moz-user-select: none; -ms-user-select: none;';
    document.body.appendChild(opt_panel);

    var top = document.createElement('div');
    top.style.cssText = 'height: 24px; line-height: 24px; font-size: 12px; overflow: hidden; margin: 0 auto; padding: 0 5px;';
    top.className = 'img-opt-top';
    top.innerHTML = '<div class="top_url" style="overflow: hidden; white-space: nowrap; text-overflow: ellipsis; width: 100%; height: 24px;"></div><style>.img-opt-item{color: #000000; transition: all 0.2s linear; -webkit-transition: all 0.1s linear;}.img-opt-item:hover{background: #eeeeee;}</style>';
    opt_panel.appendChild(top);

    var item = document.createElement('div');
    item.style.cssText = 'width: 100%; height: 24px; line-height: 24px; cursor: pointer;';
    item.className = 'img-opt-item';
    item.textContent = i18n[lang]['utp'];
    item.setAttribute('img-opt', 'up2picbed');
    opt_panel.appendChild(item);
}

function hide_panel() {
    if (!opt_panel || !opt_panel.parentElement) return;
    img_src = null;
    opt_panel.parentElement && opt_panel.parentElement.removeChild(opt_panel);
}

function upload_file(data) {
    if (xhr.readyState != 0) xhr.abort();
    xhr.onreadystatechange = function () {
        if (xhr.readyState === 4) {
            if (xhr.status === 200) {
                var res = JSON.parse(xhr.responseText);
                console.log(res);
                if (res.code === 0) {
                    img_src = res.src
                    opt_panel.getElementsByClassName('top_url')[0].style.marginTop = '0px';
                    opt_panel.getElementsByClassName('top_url')[0].textContent = i18n[lang]['us'];
                    setTimeout(hide_panel, 3000);
                } else {
                    opt_panel.getElementsByClassName('top_url')[0].style.marginTop = '0px';
                    opt_panel.getElementsByClassName('top_url')[0].textContent = res.msg;
                }
            }
        }
    };
    xhr.upload.onprogress = function (event) {
        opt_panel.getElementsByClassName('top_url')[0].style.marginTop = '0px';
        opt_panel.getElementsByClassName('top_url')[0].textContent = i18n[lang]['iu'];
    };
    xhr.onerror = function () {
        alert(i18n[lang]['uf']);
    };
    var form = new FormData();
    xhr.open('POST', setting.server_url);
    xhr.setRequestHeader('Authorization', 'LinkToken ' + setting.link_token);
    form.append(setting.upload_name, data);
    form.append('origin', 'userscript/' + GM_info.script.version);
    xhr.send(form);
    opt_panel.getElementsByClassName('top_url')[0].style.marginTop = '-48px';
}

function upload_blob_url(url) {
    if (!url) return;
    var req = new XMLHttpRequest();
    req.open('GET', url);
    req.responseType = 'blob';
    req.onload = function () {
        reader.readAsDataURL(req.response);
    };
    req.onerror = function () {
        alert(i18n[lang]['uf']);
    };
    req.send();
}

document.addEventListener('mousedown', function (event) {
    if (disable_contextmenu === true) {
        document.oncontextmenu = null;
        disable_contextmenu = false;
    }
    //event.button: 0是单击，2是右击
    if (event[setting.hot_key] === true && event.button === 2) {
        if (event.target.tagName.toLowerCase() == 'img' && event.target.src != null) {
            if (opt_panel === null) create_panel();
            else {
                if (last_update != GM_getValue('timestamp', 0)) {
                    last_update = GM_getValue('timestamp', 0);
                    opt_panel.parentElement && opt_panel.parentElement.removeChild(opt_panel);
                    create_panel();
                } else document.body.appendChild(opt_panel);
            }
            opt_panel.style.left = (document.documentElement.offsetWidth + (document.documentElement.scrollLeft || document.body.scrollLeft) - event.pageX >= 200 ? event.pageX : event.pageX >= 200 ? event.pageX - 200 : 0) + 'px';
            opt_panel.style.top = (event.pageY + opt_panel.offsetHeight < (document.documentElement.scrollTop || document.body.scrollTop) + document.documentElement.clientHeight ? event.pageY : event.pageY >= opt_panel.scrollHeight ? event.pageY - opt_panel.offsetHeight : 0) + 'px';
            disable_contextmenu = true;
            document.oncontextmenu = function () {
                return false;
            };
            opt_panel.getElementsByClassName('top_url')[0].style.marginTop = '0px';
            opt_panel.getElementsByClassName('top_url')[0].textContent = event.target.src;
            img_src = event.target.src;
        } else hide_panel();
    } else if (opt_panel != null) {
        //打开panel后的单击、右击页面动作处理
        if (event.target.compareDocumentPosition(opt_panel) === 10 || event.target.compareDocumentPosition(opt_panel) === 0) {
            if (event.target.className === 'img-opt-item' && event.button === 0) {
                //点击了panel内的item
                if (event.target.getAttribute('img-opt') === "up2picbed") {
                    if (/^(?:blob:|filesystem:)/.test(img_src)) upload_blob_url(img_src);
                    else upload_file(img_src)
                }
            } else if (event.button != 0) hide_panel();
        } else hide_panel();
    }
}, true);