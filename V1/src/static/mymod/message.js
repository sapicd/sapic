layui.define("jquery", function (exports) {
    'use strict';
    var $ = layui.jquery,
        MOD_NAME = "message",
        DEFAULTS = {
            iconFontSize: "20px", //图标大小
            messageFontSize: "12px", //信息字体大小
            showTime: 3000, //消失时间
            align: "right", //显示的位置
            positions: { //放置信息的范围
                top: "10px",
                bottom: "10px",
                right: "10px",
                left: "10px"
            },
            type: "info", //消息的类型，还有success,error,warn等
        };

    /**
     * 构造类
     */
    function Message(setting) {
        this.container = null;
        this.opts = $.extend({}, DEFAULTS, setting);
        this.init();
    }

    Message.prototype.setting = function (key, val) {
        if (arguments.length === 1) {
            if ("object" === typeof key) {
                for (var k in key) {
                    this.opts[k] = key[k]
                }
            }
        } else if (arguments.length === 2) {
            if ("string" === typeof key) {
                this.opts[key] = val;
            }
        }
    }
    /**
     * 用于添加相应的dom到body标签中
     */
    Message.prototype.init = function () {
        var domStr = "<div class='m-message' style='top:" +
            this.opts.positions.top +
            ";right:" +
            this.opts.positions.right +
            ";left:" +
            this.opts.positions.left +
            ";width:calc(100%-" +
            this.opts.positions.right +
            this.opts.positions.left +
            ");bottom:" + this.opts.positions.bottom +
            "'></div>"
        this.container = $(domStr);
        this.container.appendTo($('body'))
    }
    /**
     * 用于添加消息到相应的标签中
     * @param text: 具体的消息
     * @param type: 消息的类型
     * @param align: 本次消息显示位置
     * @param time: 本次消息超时
     */
    Message.prototype.push = function (text, type, align, time) {
        if (!text) return false;
        var domStr = "",
            type = type || this.opts.type,
            align = align || this.opts.align;
        domStr += "<div class='c-message-notice' style='" +
            "text-align:" + align + ";'><div class='m_content'><i class='";
        switch (type) {
            case "info":
                domStr += "saintic-icon saintic-icon-info msg-icon-info";
                break;
            case "success":
                domStr += "saintic-icon saintic-icon-success msg-icon-success";
                break;
            case "error":
                domStr += "saintic-icon saintic-icon-error msg-icon-error";
                break;
            case "warn":
                domStr += "saintic-icon saintic-icon-warn msg-icon-warn";
                break;
            default:
                throw "传递的参数type错误，请传递info/success/error/warn中的一种";
                break;
        }
        domStr += "' style='font-size:" +
            this.opts.iconFontSize +
            ";'></i><span style='font-size:" +
            this.opts.messageFontSize +
            ";'>" + text + "</span></div></div>";
        var $domStr = $(domStr).appendTo(this.container);
        this._hide($domStr, time);
    }
    /**
     * 隐藏消息
     * @param $domStr: 该消息的jq对象
     * @param time: 超时时间，默认取opts配置
     */
    Message.prototype._hide = function ($domStr, time) {
        setTimeout(function () {
            $domStr.fadeOut(1000);
        }, time || this.opts.showTime);
    }
    //输出接口
    exports(MOD_NAME, new Message());
});