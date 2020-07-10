.. _picbed-hook:

=======
钩子
=======

或者称为扩展、插件吧，本质就是增强某个功能点的代码段，当然是用Python实现，
分为内置和第三方。

实现这一功能的核心在于钩子管理器：HookManager类（libs/hook.py），感兴趣可以
看下源码，是提取Flask-PluginKit部分加上其他东西实现的。

--------

.. _picbed-local-hook:

内置钩子
-----------

所属本地，不允许删除，只能禁用、启用，目前有两个内置，up2local和token，
分别是将上传的图片保存到本地、API可以使用Token（LinkToken）认证。

.. versionchanged:: 1.1.0

    内置增加了4个，将我之前写的常用的对象存储内置集成了，不过默认是禁用的。

- up2local

    将上传的图片保存到本地（picbed源码目录src/static/upload），默认保存图片
    的钩子。

- up2upyun
    
    将上传的图片保存到又拍云的 `USS云存储服务 <https://www.upyun.com/products/file-storage>`_

    使用方法：启用钩子，刷新控制台页面，在 **站点管理-网站设置** 底部的
    钩子配置区域配置又拍云相关信息， 如加速域名、Bucket、用户名及密码等，
    并在上传区域中 **选择存储后端为up2upyun** 即可，后续图片上传时将会
    保存到又拍云。

- up2qiniu

    将上传的图片保存到七牛云的 `KODO对象存储服务 <https://www.qiniu.com/products/kodo>`_

    使用方法：参考又拍云的使用即可，配置加速域名、Bucket、AK及SK等（在七牛云
    个人中心-密钥管理可以拿到AK、SK）。

- up2oss

    将上传的图片保存到阿里云 `OSS对象存储 <https://www.aliyun.com/product/oss>`_

    使用方法：同上，配置要求的AK及SK可以在阿里云管理控制台-AccessKey密钥管理
    中拿到；允许使用RAM子用户的密钥（允许编程访问），要求拥有OSS管理权限即可。

- up2cos

    用来将上传的图片保存到腾讯云 `COS对象存储 <https://cloud.tencent.com/product/cos>`_

    使用方法：同上，配置加速域名、Bucket、SecretID及Key等（在腾讯云控制台-访问管理-访问密钥-API密钥管理中可以拿到SecretId、SecretKey；允许使用子用户的密钥，要求拥有COS管理权限即可）。

.. versionchanged:: 1.5.0

- up2github

    用来将上传的图片保存到 `GitHub <https://github.com>`_ 公开仓库，您需要拥有github账号，并获取personal access token。

    定位到：https://github.com/settings/tokens/new，勾选repo权限，生成后会有
    下图所示token，只会出现这一次，保存好！

    |picbed_github_token|

    之后[可选]创建一个public仓库，或使用已有仓库。

    接下来是开启GitHub钩子并配置，上传的图片会存到“仓库/存储根目录”下，允许
    多级子目录和 `自定义域名 <https://help.github.com/github/working-with-github-pages/about-custom-domains-and-github-pages>`_ 
    （默认是raw.githubusercontent.com），当然，
    不用域名而使用JsDelivr也是极好的，直接全网CDN（+免费图床套餐）！

    |picbed_github_hook|

    .. tip::

        JsDelivr能直接把github仓库CDN化，所以很多静态资源放github，用jsdelivr
        访问，实现CDN效果。
        
        不过注意勾选上使用JsDelivr，由于CDN缓存效果，删除时，图片一段时间
        仍然可以访问。

        如果使用自定义域名（请参考官方文档设置），其需要github构建，所以
        刚上传的图片也不能立刻访问，需要等构建成功。

- up2gitee

    用来将上传的图片保存到 `Gitee（码云） <https://github.com>`_ ，生成
    `私人令牌 <https://gitee.com/profile/personal_access_tokens/new>`_ ，勾选
    projects权限，其他不需要。

    同样保存好令牌，创建一个公开仓库或使用已有仓库。

    开启Gitee钩子并配置，没有JsDelivr支持，其他与github类似。

    |picbed_gitee_hook|

.. _picbed-third-hook:

第三方钩子
------------

非内置的钩子所属均为第三方，我发布的第三方可以在
`GitHub搜索 <https://github.com/search?q=user%3Astaugur+picbed>`_

第三方是通过pip、easy_install等安装到本地环境中的模块、包。

使用第三方钩子需要先在服务器安装模块，然后管理员在控制台-站点管理-钩子扩展
添加第三方钩子 **模块名称** 。

上面我发布的第三方基本都已经发布到pypi，所以可以使用pip直接安装：

.. code-block:: bash

    $ pip install up2smms up2superbed

目前已有的钩子及简介：
=======================

before_request
^^^^^^^^^^^^^^^^^

即在flask的before_request钩子函数内运行的方法，无传参（return无效果）。

after_request
^^^^^^^^^^^^^^^^^

即在flask的after_request钩子函数内运行的方法，传递response参数。

upimg_save
^^^^^^^^^^^^^^

api上传在保存图片时使用的钩子，传递可变参数filename、stream、upload_path，分别是：文件名、二进制数据、上传路径。

另外，钩子中还应该有个upimg_delete方法用以删除图片[可选]，传递可变参数sha、upload_path、filename、basedir、save_result，分别是：图片唯一id、上传路径、文件名、基础路径、upimg_save返回结果。

profile_update
^^^^^^^^^^^^^^^^^^

用户成功修改个人资料时触发此钩子方法，传递关键字参数nickname、avatar

第三方认证相关的几个钩子
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

site_auth      布尔值，True定义了自身是个第三方认证的钩子

login_handler  登录页面处理器，控制了/login路由，默认返回程序自身登录页

login_api      登录接口处理器，必须

logout_handler 登出动作处理器，必须

管理员控制台钩子配置处有一个第三方认证，钩子只有设置了 ``site_auth = True`` 才被认为是一个第三方认证钩子。

这一块至少需要实现三个函数：login_api、logout_handler、before_request，
分别处理登录登出动作以及每次请求登录态判断，少一个，程序都会进入默认处理，
那这个钩子恐怕就没什么意义了。

login_handler是登录页面，其通过ajax登录，传递username、password、remember三个
参数，基本可以不用管，当然，如果你的登录参数复杂，可以定义此函数返回自定义
登录页面，要求返回值要是Flask.Response的子类，示例：

.. code-block:: python

    from flask import make_response

    site_auth = True
    
    def login_handler():
        return make_response("""<form>
            <input name=other-user></input>
            <input name=encrypted-pass></input>
            <button>登录</button></form>
        """)

login_api是登录动作处理器，默认登录页面是ajax提交给接口，验证用户名密码，
通过后设置cookie登录态。

必须要自定义此方法，程序默认会传递可变参数：username, password, set_state, max_age, is_secure，
当然你也可以不接收，转而使用request另行处理（如果自定义了login_handler），
另外要求返回值要是Flask.Response的子类，而且要设置登录态，
比如cookie、session（如果采用默认登录页面，返回类型要求是JSON）。

.. code-block:: python

    from flask import request, jsonify

    def login_api(*default_args):
        user = request.form.get("other-user")
        passwd = request.form.get("encrypted-pass")
        return jsonify(code=0, msg="ok")

logout_handler是登出动作处理器，配合login_api的登录态设置方法，比如是cookie
要设置清除cookie，是session要删除键值。

before_request是flask的一种钩子，每次请求都先经过它“预处理”一下再交给路由
函数，自定义认证需要通过它设置 ``g.siginin = True/False`` 设定登录成功与否
和 ``g.userinfo`` 登录用户的信息，必须字段username，其他字段is_admin、avatar、nickname等。

.. code-block:: python

    def before_request():
        if check_with_cookie_or_session_login_ok:
            g.siginin = True
            g.userinfo = dict(
                username='xxx',
                is_admin=0,
                avatar='',
                nickname='',
            )

.. tip::

    可以结合profile_update方法更新一些字段。另外可以参考现有案例
    `picbed-ssoclient <https://github.com/staugur/picbed-ssoclient>`_ 。

API
^^^^^^^

程序有一个API接口是专门给钩子准备的，端点是 ``api.ep`` ，
url是 ``/api/extendpoint`` ，仅支持POST方法，它从URL查询参数获取两个值：

Object：即钩子模块名；

Action：钩子方法

钩子管理器定位到Object执行Action函数，Action如果返回Flask.Response子类，
那么路由函数则会直接返回Action函数执行结果。

假设一个钩子helloworld，定义如下：

.. code-block:: python

    from flask import jsonify

    def welcome():
        return jsonify(hello="world")

上述钩子加入picbed，请求如下：

.. code-block:: bash

    $ curl -XPOST "http://your-picbed-url/api/extendpoint?Object=helloworld&Action=welcome"
    {"hello": "world"}

模板中钩子插入点
====================

与上面不同，这些只作用在模板内，用来在页面某位置插入HTML代码。

使用方法是，在钩子内，用 ``intpl_NAME`` 赋值（intpl_是固定前缀），可以定义成字符串或者函数。

如果是函数，那么会先执行函数（结果必须是字符串），
其结果再判断是模板文件还是HTML代码。

如果以 ``.html, .htm, .xhtml`` 结尾，则认为是模板文件，否则是
HTML模板代码，前者以render_template渲染，后者以render_template_string渲染，
也就是说可以使用flask在模板内的东西，url_for、g、request等。

目前模板中可用的NAME如下：

- sitesetting

  管理员控制台站点设置下与上传设置之间，表单内容。

  .. code-block:: html

    intpl_sitesetting = '''
    <div class="layui-form-item">
        <label class="layui-form-label">提示</label>
        <div class="layui-input-block">
            <input>表单样式参考layui</input>
        </div>
    </div>
    '''

- hooksetting

  管理员控制台钩子设置下，表单内容，格式参考上面。

- profile

  用户个人资料下，表单内容，格式参考上面。

- usersetting

  用户设置的站点个性化设置下面，表单内容，格式参考上面。

- before_usersetting

  用户设置的站点个性化设置上面，表单内容，格式参考上面。

.. tip::

  由于前端页面使用 `Layui <https://www.layui.com/>`_ 框架，所以模板内表单
  您需要对其格式有所了解。

如何编写钩子？
----------------

可参考内置钩子和已有第三方。

1. 使用Python编写，兼容2.7和3.5+

2. 基本上需要一些对Flask框架的了解

3. 
  实际编写中，就是一个模块，复杂一点可以定义成包。
  编写时需要定义元数据(必须包含version和author)，参照函数运行环境，
  灵活使用Flask的“全局”变量，之后就可以开搞了。

  .. code-block:: python

    __version__ = '版本号'
    __author__ = '作者'
    __hookname__ = '直接定义钩子模块名称，否则默认是文件模块名'
    __state__ = 'enabled/disabled'  # 状态：启用(默认)/禁用
    __description__ = '描述'
    __catalog__ = '分类'

    #: Your Code Here.

  可以参照 `Flask-PluginKit如何开发第三方插件 <https://flask-pluginkit.rtfd.vip/zh_CN/latest/tutorial/third-party-plugin.html#how-to-develop-plugins>`_ ，
  除了第一步开发细节，其他流程差不多。

.. |picbed_github_token| image:: /_static/images/picbed_github_token.png
.. |picbed_github_hook| image:: /_static/images/picbed_github_hook.png
.. |picbed_gitee_hook| image:: /_static/images/picbed_gitee_hook.png
