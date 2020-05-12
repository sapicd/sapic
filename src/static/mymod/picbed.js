layui.define(["layer", "util", "element"], function (exports) {
    'use strict';
    var $ = layui.jquery,
        layer = layui.layer,
        util = layui.util,
        device = layui.device(),
        element = layui.element;
    //禁止嵌套
    if (window != top) {
        top.location.href = location.href;
    }
    //阻止IE访问
    if (device.ie) {
        layer.alert('不支持IE浏览器访问，推荐使用Firefox、Chrome。', {title:false});
    }
    //右下角工具
    util.fixbar({
        bgcolor: '#009688'
    });
    //复制接口
    var Clipboard = (function (window, document, navigator) {
        var textArea,
            copy;
        // 判断是不是ios端
        function isOS() {
            return navigator.userAgent.match(/ipad|iphone/i);
        }
        //创建文本元素
        function createTextArea(text) {
            textArea = document.createElement('textArea');
            textArea.value = text;
            document.body.appendChild(textArea);
        }
        //选择内容
        function selectText() {
            var range,
                selection;
            if (isOS()) {
                range = document.createRange();
                range.selectNodeContents(textArea);
                selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(range);
                textArea.setSelectionRange(0, 999999);
            } else {
                textArea.select();
            }
        }
        //复制到剪贴板
        function copyToClipboard() {
            try {
                if (document.execCommand("Copy")) {
                    layer.msg("复制成功！", {
                        icon: 1
                    });
                } else {
                    layer.msg("复制失败！请手动复制！", {
                        icon: 0
                    });
                }
            } catch (err) {
                layer.msg("复制失败！请手动复制！", {
                    icon: 2
                });
            }
            document.body.removeChild(textArea);
        }
        copy = function (text) {
            createTextArea(text);
            selectText();
            copyToClipboard();
        };
        return {
            copy: copy
        };
    })(window, document, navigator);
    //公共接口
    var api = {
        ajax: function (url, success, options) {
            /*
                Ajax提交
                @param url string: 请求路径
                @param success function: success为成功后回调函数
                @param options object:
                    async是否异步; 
                    post,put,delete等方法所需data;
                    error为发生异常时或success返回中code不为0时回调函数;
                    beforeSend为请求前回调函数;
                    complete为完成请求后回调;
                    msgprefix表示success返回code不为0时提示消息的前缀。
            */
            var that = this,
                urltype = typeof url === 'string',
                successtype = typeof success === "function",
                optionstype = typeof options === "object";
            if (!url || !urltype) {
                return false;
            }
            if (success) {
                if (!successtype) {
                    return false;
                }
            }
            if (options) {
                if (!optionstype) {
                    return false;
                }
            } else {
                options = {};
            }
            return $.ajax({
                url: url,
                async: options.async || true,
                method: options.method || 'post',
                dataType: options.dataType || 'json',
                contentType: options.contentType,
                data: options.data || {},
                beforeSend: options.beforeSend ? options.beforeSend : function () {},
                success: function (res) {
                    if (res.code === 0 || res.success === true) {
                        success && success(res);
                    } else {
                        if (options.msgprefix != false) {
                            layer.msg(options.msgprefix || '' + res.msg || res.code);
                        }
                        options.fail && options.fail(res);
                    }
                },
                error: function (XMLHttpRequest, textStatus, errorThrown) {
                    layer.msg("系统异常，请稍后再试，状态码：" + XMLHttpRequest.status + "，" + textStatus, {
                        icon: 2
                    });
                },
                complete: options.complete ? options.complete : function () {}
            });
        },
        Clipboard: Clipboard,
        isURL: function (str_url, only_http) {
            var re_weburl = new RegExp(
                "^" +
                // protocol identifier
                "(?:(?:https?|ftp)://)" +
                // user:pass authentication
                "(?:\\S+(?::\\S*)?@)?" +
                "(?:" +
                // IP address dotted notation octets
                // excludes loopback network 0.0.0.0
                // excludes reserved space >= 224.0.0.0
                // excludes network & broacast addresses
                // (first & last IP address of each class)
                "(?:[1-9]\\d?|1\\d\\d|2[01]\\d|22[0-3])" +
                "(?:\\.(?:1?\\d{1,2}|2[0-4]\\d|25[0-5])){2}" +
                "(?:\\.(?:[1-9]\\d?|1\\d\\d|2[0-4]\\d|25[0-4]))" +
                "|" +
                // host name
                "(?:(?:[a-z\\u00a1-\\uffff0-9]-*)*[a-z\\u00a1-\\uffff0-9]+)" +
                // domain name
                "(?:\\.(?:[a-z\\u00a1-\\uffff0-9]-*)*[a-z\\u00a1-\\uffff0-9]+)*" +
                // TLD identifier
                "(?:\\.(?:[a-z\\u00a1-\\uffff]{2,}))" +
                ")" +
                // port number
                "(?::\\d{2,5})?" +
                // resource path
                "(?:/\\S*)?" +
                "$", "i"
            );
            if (str_url && re_weburl.test(str_url)) {
                if (only_http === true) {
                    if (str_url.startsWith("http://") || str_url.startsWith('https://')) {
                        return true;
                    } else {
                        return false;
                    }
                } else {
                    return true;
                }
            } else {
                return false;
            }
        },
        escape2Html: function (str) {
            return $("<div>").html(str).text();
        },
        isMobile: (navigator.userAgent.match(/(phone|pad|pod|iPhone|iPod|ios|iPad|Android|Mobile|BlackBerry|IEMobile|MQQBrowser|JUC|Fennec|wOSBrowser|BrowserNG|WebOS|Symbian|Windows Phone|Opera Mini)/i)) ? true : false,
        str2star: function (str, start = 4, end = -4) {
            return str.length > (start + Math.abs(end)) ? str.substr(0, start) + '****' + str.substr(end) : str;
        },
        getHash: function (str, caseSensitive) {
            /**
             * 获取字符串的哈希值
             * @param {String} str
             * @param {Boolean} caseSensitive
             * @return {Number} hashCode
             */
            if (!caseSensitive) {
                str = str.toLowerCase();
            }
            // 1315423911=b'1001110011001111100011010100111'
            var hash = 1315423911,
                i, ch;
            for (i = str.length - 1; i >= 0; i--) {
                ch = str.charCodeAt(i);
                hash ^= ((hash << 5) + ch + (hash >> 2));
            }
            return (hash & 0x7FFFFFFF);
        },
        arrayContains: function (arr, obj) {
            var i = arr.length;
            while (i--) {
                if (arr[i] === obj) {
                    return true;
                }
            }
            return false;
        },
    };
    //输出接口
    exports('picbed', api);
});