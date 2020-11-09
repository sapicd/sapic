.. _picbed-usgae-pycli:

=================
使用说明 - cli.py
=================

.. versionadded:: 1.6.0

相关代码在源仓库的 `cli目录下 <https://github.com/staugur/picbed/blob/master/cli>`_

脚本是 `cli.py <https://github.com/staugur/picbed/blob/master/cli/cli.py>`_ ，
单独使用，用以命令行形式上传本地图片，不依赖第三方模块，支持python2.7、3.x

Windows下可以使用cli/picbed-cli.exe，打包好的，无需本地安装Python环境。

.. versionchanged:: 1.9.0
    支持上传临时图片

.. versionchanged:: 1.10.0
    style允许自行扩展；默认输出由打印每个结果（json object）改为打印整体结果（json array）

.. versionchanged:: 1.10.5
    增加 `line` 输出风格；增加copy选项，复制图片上传后的url，支持markdown、rST格式。

.. code-block:: bash

    $ python cli.py -h
    usage: picbed cli [-h] [-u PICBED_URL] [-t PICBED_TOKEN] [-a ALBUM] [-d DESC]
                      [-e EXPIRE] [-s STYLE] [-c {url,md,rst}]
                      file [file ...]

    More docs to https://picbed.rtfd.vip/cli.html

    positional arguments:
      file                  Local file

    optional arguments:
      -h, --help            show this help message and exit
      -u PICBED_URL, --picbed-url PICBED_URL
                            The picbed upload api url.
                            Or use environment variable: picbed_cli_apiurl
      -t PICBED_TOKEN, --picbed-token PICBED_TOKEN
                            The picbed LinkToken.
                            Or use environment variable: picbed_cli_apitoken
      -a ALBUM, --album ALBUM
                            Set image album
      -d DESC, --desc DESC  Set image title(description)
      -e EXPIRE, --expire EXPIRE
                            Set image expire(seconds)
      -s STYLE, --style STYLE
                            The upload result output style: { default, typora, line }.
                            Or, allows the use of "module.function" to customize the output style.
      -c {url,md,rst}, --copy {url,md,rst}
                            Copy the uploaded image url type to the clipboard for win/mac/linux.
                            By the way, md=makrdown, rst=reStructuredText

-u: 指定图床的服务地址，http[s]://你的picbed域名
    可以通过环境变量 **picbed_cli_apiurl** 设定

-t: 设置LinkToken用以认证、授权，要求拥有 ``api.upload`` 的 ``post`` 权限
    可以通过环境变量 **picbed_cli_apitoken** 设定

-a: 设置相册名（可以覆盖LinkToken设置的默认相册）

-d: 设置图片描述

-e: 指定过期时间（秒），作为临时图片上传

-s: 指定输出风格，支持typora、default、{DIY}

    - typora: 专为Typora编辑器上传图片准备的格式

    - line: 跟typeora类似，只不过没有先打印upload success，仅打印每个图片url

    - {DIY}: 编写Python实现自定义输出，其格式是: **module.function**
        cli.py会尝试加载module模块，执行其function函数，
        传参是result（列表，每个元素都是字典，是图片上传的响应结果）

        示例：
    
        .. code-block:: bash

            $ cat output.py
            import json
            def pretty(result):
                for i in result:
                    print(json.dumps(i))
            $ python cli.py -s output.pretty upload_file...

    - default: 默认值，打印JSON格式的整体结果（即result）

-c: 即开启复制，脚本会识别操作系统，复制上传后的图片url到系统剪贴板

    - Windows下使用DOS命令clip，执行成功，有消息通知（仅win10）

    - MacOS下使用pbcopy命令，执行成功，有消息通知

    - Linux下使用xclip，需要自行安装，但是字符终端测试失败，预计仅用于图形模式。

    部分情况会复制失败，比如没有上传成功的图片、上传前就出错了等。

    copy允许设定复制图片上传地址的格式，支持url、md、rst格式

    比如上传1.png，上传后返回url是http://cdn.com/1.png，那么ct=url会直接复制这个url，
    ct=md，复制的是：`![1.png](http://cdn.com/1.png)`

    可以上传多个文件，复制的结果会用 **\\n** 连接。

应用示例
==========

作为自定义命令在使用Typora时上传图片到picbed
----------------------------------------------

`Typora <https://typora.io>`_ 是一款跨平台的Markdown编辑器，
在编写内容时可以对图片进行特殊处理，比如上传图片。

打开Typora，定位到偏好设置-图像，选择插入图片时-上传图片，上传服务设定：

上传服务：Custom Command

自定义命令：python cli.py -u {picbed url} -t {LinkToken} -s typora

测试：点击『验证图片上传选项』按钮，验证是否成功。

Windows系统的图片文件添加右键菜单：upload to picbed
-----------------------------------------------------

如果你想在Windows资源管理器中，任意图片右键就能上传到picbed的话，OpenWithPlusPlus是个
不错的程序。

github: `stax76/OpenWithPlusPlus <https://github.com/stax76/OpenWithPlusPlus>`_

在release下载打包的zip压缩包解压，打开程序，先install（也许你需要重启下资源管理器或电脑），
之后添加add新增右键菜单，部分参数解释如下：

Path：是python程序路径，如果你的Windows操作系统没有Python也可以，cli.py已经打包成exe，
位于cli/picbed-cli.exe

Arguments: cli.py文件路径及参数，如果是打包的exe，就不要cli.py，只需要后面参数，其中
`-ct` 参数是复制的类型，默认url，可选md（markdown）、rst（reStructuredText）

- 如果本地有python环境，参照下图示例填写：

.. image:: https://static.saintic.com/picbed/staugur/2020/11/06/openwithpp-1.png

- 如果本地无python环境，参照下图示例填写：

.. image:: https://static.saintic.com/picbed/staugur/2020/11/06/openwithpp-2.png

ps: 图片名以中文开头上传失败，但允许在其他位置。

MacOS系统添加右键菜单
-----------------------

环境：macOS Cataline 10.15

打开启动台-自动操作，新建文稿，类型是快速操作，选取确定后，按照如下示例填写：

.. image:: https://static.saintic.com/picbed/staugur/2020/11/06/automator-rightmenu.png

工作流程收到当前：**图像文件**

位于：**访达**

图像/颜色：随便

下面的工作流程，拖拽资源库-实用工具-运行shell脚本，
shell选择 **/bin/bash** ，传递输入选择 **作为自变量** ，脚本内容：

.. code-block:: bash

    python ~/code/picbed/cli/cli.py -u https://picbed.pro -t xxx -c md "$@"

ps: cli.py需要下载到本地，路径自适应修改。

ps: 图片名以中文开头上传失败，但允许在其他位置。
