.. _picbed-usgae:

============
使用说明
============

.. note::

    使用就很简单了，Web应用，点点看看。

    IE系列支持有限，建议使用现代化浏览器，推荐Firefox、Chrome。

--------

.. _picbed-cli:

0. 命令行
----------

即flask子命令，其中 ``flask sa create`` 是用来创建用户（管理员），请注意约束：
这个入口应该是唯一一个创建管理员用户的方法。

创建管理员用户可以在启动程序前后。

.. code-block:: bash

    $ flask sa --help
    Usage: flask sa [OPTIONS] COMMAND [ARGS]...

        Administrator commands

    Options:
        --help  Show this message and exit.

    Commands:
        clean   清理系统
        create  创建账号

    $ flask sa create --help
    Usage: flask sa create [OPTIONS]

        创建账号

    Options:
        -u, --username TEXT       用户名
        -p, --password TEXT       用户密码
        --isAdmin / --no-isAdmin  是否为管理员  [default: False]
        -a, --avatar TEXT         头像地址
        -n, --nickname TEXT       昵称
        --help                    Show this message and exit.

1. 个人中心
-------------

个人中心包含个人资料、修改密码、用户设置、我的图片等。

个人资料只是简单的用户名、昵称、头像等，但除此之外，还有一个Token信息。

.. _picbed-token:

1.1 Token
+++++++++++

个人资料中值得一提的是Token，它是目前唯一一种能在API请求中认证用户的方法，
实际上，这是由内置的钩子(hooks/token.py)实现的（默认启用，管理员可关闭）。

Token每个用户唯一，可以随意重置、销毁再生成，具备API所有权，一旦泄露风险极大！

Token的使用也很简单，有两种方法：

- 一是Header，使用 **"Authorization:Token 你的token值"** 

  .. code-block:: bash

    curl -XPOST -H "Authorization:Token xxx" http://picbed.example.ltd/api/upload

- 二是post body中附带token字段，例如:

  .. code-block:: bash

    curl -XPOST -d token=xxx -d other=xxx http://picbed.example.ltd/api/upload

.. warning::

    如需使用Token，那么墙裂建议使用基于它的 :ref:`LinkToken <LinkToken>` ！

.. _picbed-usersetting:

1.2 用户设置
+++++++++++++++

用户设置是您在站点中的个性化设置，仅在个人登录后有效，不会影响到其他人！
也就是说，登陆后，此处的一些设置可以覆盖管理员针对全站的设置，比如背景图。
此外，还有一些针对个人的单独设置，比如图片数量、放大度、统计开关。

.. _LinkToken:

1.2.1 LinkToken
^^^^^^^^^^^^^^^^^^

在用户设置中有一个 **Token分权引用表** ，是由内置的token钩子带来的，它基于
用户唯一的Token，配合访问控制而实现，用于安全的API调用场景。

出现LinkToken的初衷是因为我想在外部网站放置一个按钮，经过简单配置能一键上传
图片到picbed，但是好像需要鉴权，而用Token呢，放到前端页面，基本等于裸奔，所
以才有了这个以Token为基础的LinkToken。

当然，也会有泄露风险，但是设定访问权限控制，能将成本大大降低。

关于LinkToken的原理、如何配置、外部上传插件等参考专题页： :doc:`/picbed/linktoken`

.. _url-process:

1.2.2 URL后缀与应用场景
^^^^^^^^^^^^^^^^^^^^^^^^^^

就是为了实现图片处理，除了本地图片，又拍、七牛、阿里、腾讯等对象存储都有
图片处理的功能，在图片链接后加一个分隔符和处理指令，能实现裁剪、旋转、水印
等高效处理。

picbed的URL后缀选项，就是定义分隔符和处理指令，当然由于存储图片可以是本地、
又拍云、七牛云等，且所有图片不一定保存在哪个里面，所以此处URL后缀的格式需要
注意下：

**图片保存者(钩子名称):处理图片的分隔符与指令或样式**，注意冒号，允许以逗号分隔多条！

.. tip::

    图片保存者，也就是钩子名称，可以在图片详情弹窗中看到，或者api的sender字段。

    参考 :ref:`Upload Api <picbed-api-upload>` 上传流程，图片总会保存到某一个钩子中，默认
    是本地，也就是up2local钩子，其他钩子参考 :ref:`picbed-hook` ，内置、第三方
    都会有一个钩子名。

举例 => **up2local:?v=1, up2upyun:!small**，表示使用up2local保存的图片在场景
中URL后缀增加 **?v=1** ，使用up2upyun保存的图片在场景中URL后缀增加 **!small**

单独设置URL后缀也没有意义，需要结合应用场景使用：**图片加载时、URL、HTML、rST、Markdown**，
后四个场景是在复制URL格式时（API、图片详情弹窗）使用，图片加载时是指
浏览个人中心加载我的图片时使用URL后缀（包含查看图片详情时）。

举例，保存到up2upyun又拍云的图片链接是A，设置后缀up2upyun:!small，应用到图片加载时场景，
那么在打开个人中心浏览器请求的图片链接是 **A!small**

1.2.3 用户自定义图片上传前缀和文件名
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. versionadded: 1.4.0

|picbed_userdiyimg|

v1.4.0之前上传图片只能根据全局设置保存图片的目录和文件名，现在用户可以自行
修改规则。

.. note::

    登录用户上传的图片总是位于自己的用户名下，所以无论怎么修改都不影响别人，
    但注意，如果使用规则中的默认选项（无子目录且使用文件原名），以前上传的
    图片很有可能会被后上传的图片覆盖，而且保存图片的钩子可能不支持覆盖（目
    前内置钩子只有GitHub、Gitee不会覆盖，上传提示失败）。

.. _userscript:

1.2.4 用户脚本
^^^^^^^^^^^^^^^^^^^

用户脚本是一段代码，它们能够优化您的网页浏览体验。

安装之后，有些脚本能为网站添加新的功能，有些能使网站的界面更加易用，有些则能隐藏网站上烦人的部分内容。

运行脚本需要浏览器扩展，早期Firefox的Greasemonkey，简称GM，中文俗称为“油猴子”，
所以用户脚本通常也称为“油猴脚本”。

不过picbed的油猴脚本支持的扩展是Tampermonkey。

Tampermonkey是一款免费的浏览器扩展和最为流行的用户脚本管理器，它适用于
Chrome, Microsoft Edge, Safari, Opera Next, 和 Firefox。

官网：https://www.tampermonkey.net

请先根据浏览器安装Tampermonkey扩展，然后在用户设置中配置。

|picbed_userscript|

脚本地址： `Your Picbed URL/picbed.user.js`

只有开启用户脚本后才能产生脚本链接，不严格要求填写LinkToken，但是没有的话将
会是匿名上传且不支持脚本更新。

.. note::

    脚本更新功能不在v1.5.0中，master最新代码、1.5.1修复版及之后版本可用。

开启并保存后，点击上图开关旁边的小图标，能直接打开脚本地址，此时扩展会自动
识别出用户脚本，给出安装界面：

|picbed_userscript_install|

安装完成后，在浏览器打开任意网站，鼠标移到图片上，Windows下是Ctrl/Alt键+右击，
MacOS下使用Control/Option+点击，效果如下：

|picbed_userscript_upload|

通过Image URL方式上传，除基本图片外(含svg)，支持blob、base64类型。

限制条件：

  - 只能上传img标签的图片

  - 包裹了蒙层无法上传

  - 部分网站CSP限制导致无法上传

  - picbed无https而采集https页面图片时无法上传

  - 但是，还有一条限制！

    用户脚本在全网通过ajax上传，基本都是跨域操作，所以，管理员必须设置
    CORS Origin为*且LinkToken对Origin无限制，否则只能在允许的源站上传，而
    其他网站上传失败。

  - 简而言之，脚本必须获取到实际图片且允许上传才行

  - 另外，如果是被墙的网站图片，你的服务器在国内，那么很遗憾无法下载，应该
    会提示：未获取到图片或不允许的图片格式。

.. note::

    此用户脚本从 `Search-By-Image <https://github.com/ccloli/Search-By-Image/>`_
    移植而来，如您正在使用它，注意快捷键冲突。

.. _picbed-mypic:

1.3 我的图片
+++++++++++++

我的图片顾名思义，登录用户能看到自己上传的所有图片，点击图片显示详情弹窗，
在弹窗里可以继续复制URL、HTML、reStructuredText(rST)、Markdown格式的图片链接，
当然允许删除，不仅是逻辑删除，只要后端存储钩子支持亦会删除实际图片文件，
目前的内置钩子均支持完全删除。

图片详情中相册名是可以修改的，双击显示已有相册，点击后面的√即可提交更新。

1.4 统计图表
++++++++++++++

.. versionadded:: 1.6.0

初版的LinkToken调用统计表，展示了什么时间在什么系统、设备、浏览器上调用了
LinkToken哪个接口，以及认证与授权结果。

.. tip::

    在用户设置中有一个统计开关选项，其中LinkToken勾选后才能开启LinkToken调用
    统计。

.. _picbed-control:

2. 控制台
---------------

管理员功能，进行诸如站点设置、钩子扩展等管理（下图可能非最新内容）。

具体内容请参考 :ref:`picbed-admin`

|image1|

如图示，添加一个第三方钩子：up2smms，这个钩子可以将上传的图片保存到sm.ms公共图床。

|image2|

不过在web中添加这个钩子需要首先在部署的服务器上安装up2smms模块::

    正式版本

        $ pip install -U up2smms

    开发版本

        $ pip install -U git+https://github.com/staugur/picbed-up2smms.git@master

添加钩子成功有提示，有些会附带模板，所以需要刷新下页面，比如上面这个会在
站点设置的钩子配置区域追加模板：

|image3|

还有其他钩子，更多了解参考 :ref:`picbed-hook`

3. 上传
---------

默认情况下，只有登录用户才允许上传图片，使用命令行创建用户后，
就能登录（当然，管理员可以开启开放注册功能）。

管理员也可以在站点设置中开启匿名上传，这样未登录用户就可以上传图片了。

Web中只有首页可以上传，同时最多选择10张，默认支持jpg、jpeg、gif、bmp、png、webp（管理员可修改，可以增加有效的图片后缀，如ico、svg），每张最大10M，上传成功后可以复制多个格式的图片链接，比如HTML、Markdown、reStructuredText(rST)和URL本身。

当然也可以使用API接口上传，而且首页上传也是依托接口，另外您还可以通过HTTP
或其他图床桌面程序上传，使用Token/LinkToken做用户认证。

.. versionchanged:: 1.2.0

    - 首页支持选择或拖拽系统图片上传，粘贴图片或图片链接上传。

      需要注意的是，粘贴图片上传（Windows/MacOS快捷键：Ctrl+V/Command+V）
      支持复制浏览器内图片、系统软件内图片（QQ、微信等）、截图等上传，
      不支持操作系统内的文件。

      另外，MacOS操作系统可能会因为安全性限制导致无法粘贴其他应用图片上传。

    - API也支持了图片链接上传。

      符合 `http://` 或 `https://` 的合法URL会进入图片链接上传模式，
      :ref:`参考Upload Api <picbed-api-upload>`

3.1 以下是几个客户端(通过API)上传的示例：
+++++++++++++++++++++++++++++++++++++++++++

- 使用PicGo上传到自定义的picbed图床

  `下载PicGo <https://github.com/Molunerfinn/PicGo/releases>`_ 并安装，打开
  主界面，在 **插件设置** 中搜索 **web-uploader** 并安装，然后
  在 **图床设置-自定义Web图床** 中按照如下方式填写：

  .. code-block:: text

    url: http[s]://你的picbed域名/api/upload

    paramName: picbed

    jsonPath: src

    # 以上是匿名上传，仅在管理员开启匿名时才能上传成功
    ## 如需登录上传，请使用token(在控制台-个人资料-Token查看)，以下两种任选:
    customHeader: {"Authorization": "Token 你的Token值"}
    customBody: {"token": "你的Token值", "album: "相册名或留空"}

    ## 可用LinkToken替换Token(仅用于Header)：
    customHeader: {"Authorization": "LinkToken 你的LinkToken值"}
    customBody: {"album: "相册名或留空"}

  设置完之后选择自定义Web图床为默认图床即可。

- 使用uPic上传到自定义的picbed图床

  `下载uPic <https://github.com/gee1k/uPic>`_ 并安装，在 **偏好设置-图床** 中
  添加 **自定义**，信息如下：

  .. code-block:: text

    API地址：http[s]://你的picbed域名/api/upload

    请求方式：POST

    文件字段名：picbed

    其他字段：增加Header字段 或 增加Body字段，任选一种方式：
    - Headers数据
        key: Authorization
        value: Token 你的Token值
        ## 可用LinkToken替换Token(仅用于Header)：
        key: Authorization
        value: LinkToken 你的LinkToken值

    - Body数据
        key: token
        value: 你的Token值
        # 如需设置相册，请增加Body字段，key为album，value即相册名

    URL路径：["src"]

3.2 cli.py上传
+++++++++++++++

.. versionadded:: 1.6.0

位于源码仓库 `misc/cli.py <https://github.com/staugur/picbed/blob/master/misc/cli.py>`_
脚本，可以单独使用，用以命令行形式上传本地图片，
不依赖第三方模块，支持python2.7、3.x

.. code-block:: bash

    $ python cli.py -h
    usage: cli.py [-h] -u PICBED_URL [-t PICBED_TOKEN] [-a ALBUM]
            [-s {default,typora}]
            file [file ...]

    positional arguments:
        file                  Local file

    optional arguments:
        -h, --help          show this help message and exit
        -u PICBED_URL, --picbed-url PICBED_URL
                            The picbed upload api url
        -t PICBED_TOKEN, --picbed-token PICBED_TOKEN
                            Your LinkToken
        -a ALBUM, --album ALBUM
                            Set image album
        -s {default,typora}, --style {default,typora}
                            upload result output style

-u: 指定图床的服务地址，http[s]://你的picbed域名

-t: 设置LinkToken认证、授权，拥有 ``api.upload`` 的 ``post`` 权限

-s: 指定输出风格，默认原样返回API响应

其他：-a指定相册名称，-h查看帮助信息

**应用示例：作为自定义命令在使用Typora时上传图片到picbed**

`Typora <https://typora.io>`_ 是一款跨平台的Markdown编辑器，
在编写内容时可以对图片进行特殊处理，比如上传图片。

打开Typora，定位到偏好设置-图像，选择插入图片时-上传图片，上传服务设定：

上传服务：Custom Command

自定义命令：python cli.py -u {picbed url} -t {LinkToken} -s typora

测试：点击『验证图片上传选项』按钮，验证是否成功。

4. 钩子
--------

请转到 :doc:`/picbed/hook`

5. API
--------

请转到 :doc:`/picbed/api`

6. 数据备份
-------------

存储使用redis，内存级数据存储，可以使用
`AnotherRedisDesktopManager <https://github.com/qishibo/AnotherRedisDesktopManager/>`_ 查看redis数据，
备份、迁移可以参考我的 `这篇文章 <https://blog.saintic.com/blog/265.html>`_ 。

.. |image1| image:: /_static/images/picbed_setting.png
.. |image2| image:: /_static/images/picbed_hook.png
.. |image3| image:: /_static/images/picbed_hooksetting.png
.. |picbed_userdiyimg| image:: /_static/images/picbed_userdiyimg.png
.. |picbed_userscript| image:: /_static/images/picbed_userscript.png
.. |picbed_userscript_upload| image:: /_static/images/picbed_userscript_upload.png
.. |picbed_userscript_install| image:: /_static/images/picbed_userscript_install.png

