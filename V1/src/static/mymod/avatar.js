/*!
 * Cropper v3.1.3
 * https://github.com/fengyuanchen/cropper
 *
 * Copyright (c) 2014-2017 Chen Fengyuan
 * Released under the MIT license
 *
 * Date: 2017-10-21T10:04:29.734Z
 * 
 * 封装方法：找到UMD文件，去掉头尾，改为layer.define
 */

layui.define(["cropper", "jquery"], function (exports) {
    'use strict';
    var $ = layui.jquery,
        MOD_NAME = "avatar";

    function showSize(base64url) {
        //获取base64图片大小，返回KB数字
        var str = base64url.replace('data:image/png;base64,', '');
        var equalIndex = str.indexOf('=');
        if (str.indexOf('=') > 0) {
            str = str.substring(0, equalIndex);
        }
        var strLength = str.length;
        var fileLength = parseInt(strLength - (strLength / 8) * 2);
        // 由字节转换为KB
        var size = "";
        size = (fileLength / 1024).toFixed(2);
        var sizeStr = size + ""; //转成字符串
        var index = sizeStr.indexOf("."); //获取小数点处的索引
        var dou = sizeStr.substr(index + 1, 2) //获取小数点后两位的值
        if (dou == "00") { //判断后两位是否为00，如果是则删除00                
            return sizeStr.substring(0, index) + sizeStr.substr(index + 3, 2)
        }
        return parseInt(size);
    }

    function base64ToBlob(base64url) {
        var arr = base64url.split(','),
            mime = arr[0].match(/:(.*?);/)[1],
            bstr = atob(arr[1]),
            n = bstr.length,
            u8arr = new Uint8Array(n);
        while (n--) {
            u8arr[n] = bstr.charCodeAt(n);
        }
        return new Blob([u8arr], {
            type: mime
        });
    }

    function render(options) {
        if (!options) options = {};
        if (!(Object.prototype.toString.call(options) === '[object Object]')) {
            console.error("avatar配置项类型错误");
            return false;
        }
        var uploadElem = options.elem || "#uploadAvatar",
            imgWidth = options.imgWidth || 300,
            success = options.success;

        //在body末尾追加弹框代码
        $('body').append([
            '<!--图片裁剪框 start-->',
            '<div style="display: none" class="tailoring-container">',
            '    <div class="tailoring-content">',
            '        <div class="tailoring-content-one">',
            '            <label title="上传图片" for="chooseImg" class="l-btn choose-btn">',
            '                <input type="file" accept="image/jpg,image/jpeg,image/png" name="file" id="chooseImg" class="hidden">选择图片',
            '            </label>',
            '            <div class="close-tailoring">×</div>',
            '        </div>',
            '        <div class="tailoring-content-two">',
            '            <div class="tailoring-box-parcel">',
            '                <img id="tailoringImg">',
            '            </div>',
            '            <div class="preview-box-parcel">',
            '                <p>图片预览：</p>',
            '                <div class="square previewImg"></div>',
            '                <div class="circular previewImg"></div>',
            '            </div>',
            '        </div>',
            '        <div class="tailoring-content-three">',
            '            <button class="l-btn cropper-reset-btn">复位</button>',
            '            <button class="l-btn cropper-rotate-btn">旋转</button>',
            '            <button class="l-btn cropper-scaleX-btn">换向</button>',
            '            <button class="l-btn sureCut" id="sureCut">确定剪裁并上传头像</button>',
            '        </div>',
            '    </div>',
            '</div>',
            '<!--图片裁剪框 end-->',
        ].join(""));

        var tailoringContent = $(".tailoring-content"),
            tailoringContainer = $(".tailoring-container"),
            tailoringImg = $('#tailoringImg');

        //弹出框水平垂直居中
        (window.onresize = function () {
            var win_height = $(window).height();
            var win_width = $(window).width();
            if (win_width <= 768) {
                tailoringContent.css({
                    "top": (win_height - tailoringContent.outerHeight()) / 2,
                    "left": 0
                });
            } else {
                tailoringContent.css({
                    "top": (win_height - tailoringContent.outerHeight()) / 2,
                    "left": (win_width - tailoringContent.outerWidth()) / 2
                });
            }
        })();

        //弹出图片裁剪框
        $(uploadElem).on("click", function () {
            tailoringContainer.toggle();
        });

        //关闭裁剪框
        $('.close-tailoring').click(function () {
            tailoringContainer.toggle();
        });

        //选择图片
        $('#chooseImg').change(function () {
            var file = this;
            if (!file.files || !file.files[0]) {
                return;
            }
            var reader = new FileReader();
            reader.onload = function (evt) {
                var replaceSrc = evt.target.result;
                //更换cropper的图片
                tailoringImg.cropper('replace', replaceSrc, false); //默认false，适应高度，不失真
            }
            reader.readAsDataURL(file.files[0]);
        });

        //cropper图片裁剪
        tailoringImg.cropper({
            aspectRatio: 1 / 1, //默认比例
            preview: '.previewImg', //预览视图
            guides: false, //裁剪框的虚线(九宫格)
            autoCropArea: 0.5, //0-1之间的数值，定义自动剪裁区域的大小，默认0.8
            movable: false, //是否允许移动图片
            dragCrop: true, //是否允许移除当前的剪裁框，并通过拖动来新建一个剪裁框区域
            movable: true, //是否允许移动剪裁框
            resizable: true, //是否允许改变裁剪框的大小
            zoomable: true, //是否允许缩放图片大小
            mouseWheelZoom: true, //是否允许通过鼠标滚轮来缩放图片
            touchDragZoom: true, //是否允许通过触摸移动来缩放图片
            rotatable: true, //是否允许旋转图片
            crop: function (e) {
                // 输出结果数据裁剪图像。
            }
        });
        //旋转
        $(".cropper-rotate-btn").on("click", function () {
            tailoringImg.cropper("rotate", 45);
        });
        //复位
        $(".cropper-reset-btn").on("click", function () {
            tailoringImg.cropper("reset");
        });
        //换向
        var flagX = true;
        $(".cropper-scaleX-btn").on("click", function () {
            if (flagX) {
                tailoringImg.cropper("scaleX", -1);
                flagX = false;
            } else {
                tailoringImg.cropper("scaleX", 1);
                flagX = true;
            }
            flagX != flagX;
        });

        //裁剪后的处理
        $("#sureCut").on("click", function () {
            if (tailoringImg.attr("src") == null) {
                return false;
            } else {
                var cas = tailoringImg.cropper('getCroppedCanvas', {
                    width: imgWidth,
                    imageSmoothingQuality: "high"
                }); //获取被裁剪后的canvas
                var base64url = cas.toDataURL('image/png'),
                    base64size = showSize(base64url);
                if (success && typeof success === "function") {
                    success(base64url, base64size);
                }
                //成功后关闭裁剪框
                tailoringContainer.toggle();
            }
        });
    }

    //输出接口
    exports(MOD_NAME, {
        v: "1.0.0",
        render: render,
        base64ToBlob: base64ToBlob,
    });
});