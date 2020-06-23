/*
 * uploader.js for picbed
 *
 * https://github.com/staugur/picbed
 *
 * picbed外部上传封装
 *
 * PS：ES6模块，使用 babel-minify 仅压缩源文件
 */
'use strict';

var up2picbed = (function () {

    let version = '1.1.1';

    /* 上传类，options配置项如下
     * @param url {String}:  [必需]上传接口
     * @param elem {String}: [必需]上传绑定元素，推荐使用ID
     * @param name {String}: 上传文件域字段名，默认是picbed
     * @param size {Int}: 允许上传文件的最大值，单位Kb，默认10Mb
     * @param exts {String}:  允许上传的文件后缀集合，默认jpg|png|gif|bmp|jpeg|webp
     * @param timeout {Int}: 上传超时时间，单位毫秒，默认5000
     * @param headers {Object}: 上传自定义头，默认空
     * @param data {Object}: 上传额外body数据，默认空
     * @param success {Function}: 响应成功时的回调(2xx,304表示成功)
     * @param fail {Fcuntion}: 响应失败时的回调，与success一样传递返回值
     * @param progress {Function}: 上传进度回调，传递百分比
     */
    class Uploader {

        constructor(options) {
            if (!options.elem || !options.url) {
                this._alert("请完善参数");
                return false;
            }
            options.size = parseInt(options.size || 10 * 1024);
            options.exts = options.exts || "jpg|png|gif|bmp|jpeg|webp";
            options.name = options.name || "picbed";
            options.timeout = parseInt(options.timeout || 5000);
            options.responseType = "json";
            //当返回数据中code字段为0才触发success回调
            options.onSuccess = typeof options.success === "function" && options.success;
            //返回数据code字段不为0或响应码不是2xx、304则触发fail回调
            options.onFail = typeof options.fail === "function" && options.fail;
            //上传回调
            options.onProgress = typeof options.progress === "function" && options.progress;
            //初始化
            this.opt = options;
            this._init();
        }

        _init() {
            //绑定元素对象
            let fobj = document.querySelector(this.opt.elem),
                iname = this.opt.name;

            //构建文件域
            let iobj = fobj.parentElement.querySelector(`input[name='${iname}']`);
            if (iobj) {
                fobj.parentElement.removeChild(iobj);
            }
            iobj = document.createElement("input");
            iobj.type = "file";
            iobj.name = iname;
            iobj.style.display = "none";
            iobj.onchange = e => {
                return this._upload(this.opt, e);
            }
            fobj.parentElement.appendChild(iobj);
            fobj.onclick = () => {
                let fi = fobj.parentElement.querySelector("input[type='file']");
                fi.click();
            }
        }

        _upload(o, e) {
            /* 上传方法
             * @param o: 实例化Uploder类时传的options参数
             * @param e: 文件域在改变时传递的DOM对象，e.target可以拿到files属性
             */
            let self = this,
                size = o.size,
                exts = o.exts;

            //选择图片的FileList对象
            let files = e.target.files;
            if (!files.length) return
            const FILE = files[0];

            //判断上传图片大小
            if (size > 0) {
                if (size > 10 * 1024) size = 10 * 1024;
                let s = FILE.size / 1024;
                if (s > size) {
                    return self._alert("上传图片超过限制大小【" + size + "KB】");
                }
            }
            //判断上传图片后缀
            if (exts) {
                let EXTRE = new RegExp("(" + exts + "$)", "i");
                let ext = FILE.name.split(".");
                ext = ext[ext.length - 1];
                if (!EXTRE.test(ext)) {
                    return self._alert("不支持的图片格式【" + ext + "】");
                }
            }

            //构建post数据并发送异步请求
            let data = new FormData();
            data.append(o.name, FILE, FILE.name);
            //添加额外数据
            if (typeof o.data === 'object' && Object.keys(o.data).length !== 0) {
                for (let key in o.data) {
                    data.append(key, o.data[key]);
                }
            }
            let xhr = new XMLHttpRequest();
            xhr.timeout = o.timeout;
            xhr.responseType = o.responseType;
            xhr.open("POST", o.url, true);
            //设置请求头
            if (typeof o.headers === 'object' && Object.keys(o.headers).length !== 0) {
                for (let key in o.headers) {
                    xhr.setRequestHeader(key, o.headers[key]);
                }
            }
            xhr.upload.onprogress = function (evt) {
                let pro = Math.floor((evt.loaded / evt.total * 100));
                let width = pro + "%";
                if (pro < 50) {
                    width = ((5 - pro % 5) + pro) + "%";
                } else if (pro >= 50 && pro < 90) {
                    width = ((2 - pro % 2) + pro) + "%";
                }
                o.onProgress && o.onProgress(width);
            };
            xhr.onload = function () {
                let res = xhr.response;
                if ((xhr.status >= 200 && xhr.status < 300) || xhr.status == 304) {
                    if (typeof res === "object" && res.code === 0) {
                        o.onSuccess && o.onSuccess(res);
                    } else {
                        o.onFail && o.onFail(res);
                    }
                } else {
                    o.onFail && o.onFail(res);
                }
            };
            try {
                xhr.send(data);
            } catch (e) {
                self._alert(e.message);
            }
        }

        _alert(msg) {
            let f = (typeof layer !== "undefined" && typeof layer === "object") && layer.alert;
            if (!f) {
                if (typeof layui !== "undefined" && typeof layui === "object") {
                    layui.use("layer", function () {
                        let layer = layui.layer;
                        layer.alert(msg, {
                            title: false,
                            shade: 0.1
                        });
                    });
                } else {
                    window.alert(msg);
                }
            } else {
                f(msg, {
                    title: false,
                    shade: 0.1
                });
            }
        }
    }
    let hasElem = function (id_or_class) {
        return document.querySelector(id_or_class) ? true : false;
    };
    //获取js本身
    let getSelf = function () {
        let jsSelf = document.currentScript ? document.currentScript : document.getElementsByTagName('script')[document.getElementsByTagName('script').length - 1];
        if (jsSelf && jsSelf.getAttribute("src") && jsSelf.getAttribute("src").indexOf("uploader.js") > -1) {
            return jsSelf;
        } else {
            let js = document.scripts,
                last = js.length - 1;
            for (let i = last; i > 0; i--) {
                if (js[i].readyState === 'interactive') {
                    jsSelf = js[i]
                    break;
                }
            }
            return jsSelf;
        }
    }();
    /* opt选项用于构造Uploader类，无值时读取dataset自身的初始化参数，支持如下：
     * @param url: [必需]picbed上传接口地址
     * @param elem: [默认#up2picbed]绑定上传的button元素
     * @param name: [注意]上传文件域字段名，默认是picbed，一般不用设置，除非管理员修改过默认字段
     * @param auto: [注意]当值为true时脚本会自动初始化，否则需要在手动调用up2picbed函数初始化elem上传
     * @param token: [建议]picbed上传所需的LinkToken值，当然允许匿名可以省略
     * @param album: 定义上传图片所属相册，留空表示默认使用LinkToken设定值（仅当LinkToken认证成功此项才有效）
     * @param style: 仅当值为false时有效，会取消自动设置elem的内联样式
     * @param size: 允许上传的图片大小，单位Kb，最大10Mb
     * @param exts: 允许上传的图片后缀
     * @param success: 上传成功的回调（通过字符串映射函数，传递响应结果，在脚本执行之前全局要有此函数，否则不生效）
     * @param fail: 上传失败或错误的回调（同success）
     * @param progress: 上传进度回调，传递百分比
     */
    let init = (opt) => {
        if (!opt) opt = {};
        if (!(Object.prototype.toString.call(opt) === '[object Object]')) {
            console.error("up2picbed配置项错误");
            return false;
        }
        let url = opt.url || getSelf.dataset.url,
            elem = opt.elem || getSelf.dataset.elem || "#up2picbed",
            name = opt.name || getSelf.dataset.name,
            token = opt.token || getSelf.dataset.token,
            style = opt.style || getSelf.dataset.style,
            album = opt.album || getSelf.dataset.album,
            progress = opt.progress || (getSelf.dataset.progress && window[getSelf.dataset.progress]),
            success = opt.success || (getSelf.dataset.success && window[getSelf.dataset.success]),
            fail = opt.fail || (getSelf.dataset.fail && window[getSelf.dataset.fail]),
            data = {};
        if (!hasElem(elem)) {
            console.error("up2picbed未发现有效的elem");
            return false;
        }
        if (!url) {
            console.error("up2picbed未发现有效的url");
            return false;
        }
        //当style值不为false时即自动添加elem样式
        if (!(style === "false" || style === false)) {
            if (!style) style = '';
            let [color, bgColor] = style.split(",");
            if (!color) color = "#409eff";
            if (!bgColor) bgColor = "#fff";
            document.querySelector(elem).style = `display:inline-block;margin-right:10px;padding:9px 15px;font-size:12px;background-color:${bgColor};color:${color};border:1px ${color} solid;border-radius:3px;cursor:pointer;user-select:none;`;
        }
        if (album) {
            data["album"] = album;
        }
        data["origin"] = `uploader.js/${version}`;
        return new Uploader({
            elem: elem,
            url: url,
            name: name,
            size: opt.size || getSelf.dataset.size,
            exts: opt.exts || getSelf.dataset.exts,
            data: data,
            headers: {
                "Authorization": `LinkToken ${token}`
            },
            success: typeof success === "function" ? success : res => {
                console.log(res);
            },
            fail: typeof fail === "function" ? fail : res => {
                console.error(res);
            },
            progress: progress
        });
    };
    return getSelf.dataset.auto === "true" ? init() : init;
})();
