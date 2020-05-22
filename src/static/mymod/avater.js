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

layui.define(["cropper", "layer"], function(exports) {
    'use strict';
    var $ = layui.jquery,
        layer = layui.layer;

    //弹出框水平垂直居中
    (window.onresize = function() {
        var win_height = $(window).height();
        var win_width = $(window).width();
        if (win_width <= 768) {
            $(".tailoring-content").css({
                "top": (win_height - $(".tailoring-content").outerHeight()) / 2,
                "left": 0
            });
        } else {
            $(".tailoring-content").css({
                "top": (win_height - $(".tailoring-content").outerHeight()) / 2,
                "left": (win_width - $(".tailoring-content").outerWidth()) / 2
            });
        }
    })();
    //弹出图片裁剪框
    $("#uploadAvatar").on("click", function() {
        $(".tailoring-container").toggle();
    });
    //选择图片
    $('#chooseImg').change(function() {
        var file = this;
        if (!file.files || !file.files[0]) {
            return;
        }
        var reader = new FileReader();
        reader.onload = function(evt) {
            var replaceSrc = evt.target.result;
            //更换cropper的图片
            $('#tailoringImg').cropper('replace', replaceSrc, false); //默认false，适应高度，不失真
        }
        reader.readAsDataURL(file.files[0]);
    });
    //关闭裁剪框
    $('.close-tailoring').click(function() {
        $(".tailoring-container").toggle();
    });
    //cropper图片裁剪
    $('#tailoringImg').cropper({
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
        crop: function(e) {
            // 输出结果数据裁剪图像。
        }
    });
    //旋转
    $(".cropper-rotate-btn").on("click", function() {
        $('#tailoringImg').cropper("rotate", 45);
    });
    //复位
    $(".cropper-reset-btn").on("click", function() {
        $('#tailoringImg').cropper("reset");
    });
    //换向
    var flagX = true;
    $(".cropper-scaleX-btn").on("click", function() {
        if (flagX) {
            $('#tailoringImg').cropper("scaleX", -1);
            flagX = false;
        } else {
            $('#tailoringImg').cropper("scaleX", 1);
            flagX = true;
        }
        flagX != flagX;
    });
    //裁剪后的处理
    $("#sureCut").on("click", function() {
        if ($("#tailoringImg").attr("src") == null) {
            return false;
        } else {
            var cas = $('#tailoringImg').cropper('getCroppedCanvas', {
                width: 320,
                imageSmoothingQuality: "high"
            });
            //获取被裁剪后的canvas
            var base64url = cas.toDataURL('image/png'); //转换为base64地址形式
            console.log(base64url);
            $.ajax({
                url: "/api/upload",
                method: "post",
                data: {picbed: base64url, album: 'avatar'},
                success: function(res) {
                    console.log('ok');
                    if (res.code === 0) {
                        layer.msg("头像上传成功", {icon:1}, function() {
                            $(".tailoring-container").toggle();
                        });
                        $("input[name='avatar']").val(res.src);
                    } else {
                        layer.msg(res.msg, {icon:0});
                    }
                },
                error: function(jqXHR, textStatus, errorThrown) {
                    console.log('error');
                    console.log(jqXHR);
                    layer.msg(textStatus, {icon:2});
                }
            });
            return false;
        }
    });

    //输出接口
    exports('avater', null);
});