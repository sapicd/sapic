.. _picbed-admin:

====================
使用说明 - 站点管理
====================

此为管理员的控制台配置说明，在这里可以全局设置、钩子管理等，配置项含义基本
上是简单明了，根据提示即可，下面仅说明部分重点或复杂配置。

.. note::

    - 当前内容适用于picbed的管理员
    
    - 各配置项提及的半角逗号即英文输入法下的逗号

.. _picbed-admin-gloabl:

1. 全局设置
-------------

全局设置，包括网站本身、上传细节、钩子配置。

.. _picbed-admin-site:

1.1 站点设置
===============

- CORS Origin

  设置允许跨域的源站（关于CORS请参考 `Mozilla官方文档 <https://developer.mozilla.org/docs/Web/HTTP/Access_control_CORS>`_ ）

  源站格式：http[s]://domain.name
  
  不同端口不同协议均属于不同源，可以用半角逗号分隔多个！

  允许使用 **\*** 表示允许所有源，此时不可以有其他内容！

  .. tip::

    LinkToken中所用的origin是此处的子集

- 注册选项

  - 开放注册：顾名思义，允许任何人注册，否则无法注册（接口拒绝、入口隐藏）

  - 注册审核：开启后，新注册用户能登录、操作一般事务，但不能上传

  - 禁止登录：禁止普通用户登录，包括LinkToken

- 全站公告

  位于所有页面最顶部的信息，藏青色背景，最大高度60px，允许使用部分HTML标签

.. _picbed-admin-upload:

1.2 上传设置
==============

- 上传字段

  定义通过POST表单获取图片数据的字段，默认字段是picbed， **不建议** 修改！

- 用户分组上传

  用户管理中可以给用户贴上标签，相当于分组了，在上传设置中配置分组上传，
  其格式是: **label:sender**, label是标签名、sender是存储后端的钩子名，
  允许使用逗号分隔多个规则，比如： `test:up2local`

  **一个特殊情况，匿名用户的label总是anonymous！**

  另外，用户允许设置多个标签，如果此处设定了分组上传，那么用户标签只要发现匹配则选定对应
  上传后端，不再进行后续匹配。

- 存储后端（默认存储在）

  选择保存图片的扩展钩子，本地、又拍云、GitHub等，至少有一个，否则无法保存
  图片，其扩展名就是sender，许多地方都有使用。

.. _picbed-admin-system:

1.3 系统设置
===============

将原先位于站点设置中部分选项挪移，站点设置适用于用户可见页面，系统设置更
适合定义程序内部。

- 代理服务

  用于程序请求外部HTTP[s]时，当首次请求超时、连接错误时自动调用代理。

  程序内部会发生对外请求的情况，比如使用url上传图片时，程序会请求url尝试
  获取图片内容，此时如果是被-墙-的站点图片，请求会失败的，故此可以设置一个
  代理服务器，针对http、https或某个标准域名。

  三种格式（前两种是协议，固定的）：
  
  - 设置http协议使用代理 ``http=http://your-proxy-server``
    
  - 设置https协议使用代理 ``https=http://your-proxy-server``
    
  - 设置标准域名使用代理 ``scheme://hostname=http://your-proxy-server``

  示例：

    - http=http://1.1.1.1:3128

    - https=http://user:pass@1.1.1.2:3128/
    
    - http=http://1.1.1.1:3128,https=http://user:pass@1.1.1.2:3128/

    - https=http://user:pass@1.1.1.2:3128/, https://www.google.com=http://1.1.1.1:3128

    - http://a.com=your-proxy, http://b.net=other-proxy, http://c.org=proxy

  .. note::

    对外请求超时、错误会尝试调用代理再次请求，但并不一定每个对外请求
    都如此，目前程序内部只对可能访问受限的域名请求时采用。

    要求HTTP Basic Auth认证的代理可以这么设置: `http://user:password@host/`

.. _picbed-admin-hook:

1.4 钩子设置
=============

此处有模板中钩子插入点，第三方钩子可以通过hooksetting定义表单以取值，
由管理员在此处进行配置。

此区域下有邮件服务配置相关功能，除发件人名称外，其他配置项是内置的钩子 **sendmail** 提供的。

sendmail提供三种邮件发送方式：本地、诏预开放平台（自用）、SendCloud

- 本地

  即通过本机25端口邮件服务发送，不过目前云厂商基本会禁用此功能，除此之外，本机即便能发送成功，也有可能被目标邮箱服务器丢弃或放入垃圾邮件，所以很多情况下，可以直接不使用跳过它。

- SendCloud

  SendCloud由搜狐武汉研发中心孵化的项目，是致力于为开发者提供高质量的触发邮件服务的云端邮件发送平台，为开发者提供便利的API接口来调用服务。

  官网: https://sendcloud.sohu.com

  登录进去，有系统默认发信邮箱，也可以添加自有发信域，详情参考其官方文档。

  这里需要提供一个API_USER及对应的API_KEY，还一个可选的发件人（最近发件人邮箱后缀是API_USER对应的发信域）

ps：可以通过安装 `picbed-smtp <https://github.com/staugur/picbed-smtp>`_
扩展钩子发送邮件，它通过邮箱SMTP服务发送，所以例如QQ、腾讯企业邮、网易、
新浪、阿里云等邮箱都可作为发送者。

.. _picbed-admin-hook-extension:

2. 钩子扩展
---------------

.. _picbed-admin-install-third:

2.1 安装第三方包
===================

调用pip命令，安装pypi上的包，或者直接安装诸如git、svn上的模块。

注意，如果程序在virtualenv、venv虚拟环境下启动，则会安装到其环境下，否则
安装到用户家目录下。

此功能可从 `Awesome for picbed <https://github.com/staugur/picbed-awesome/>`_
获取经过审核且开源的第三方列表，像应用商店似的进行安装，不过也保留了
原来的方式。

.. image:: /_static/images/picbed-online-hooks.png

.. note::

    会使用upgrade选项尝试升级式安装，如果不需要最新版本，注意固定版本。

.. _picbed-admin-add-third:

2.2 添加第三方钩子
=====================

将第三方包加载到程序中，作为钩子扩展功能点。

输入的是可以直接加载的模块，它很可能不是包名称，且第三方钩子文档应当给出
明确的提示。

.. _picbed-admin-usermanager:

3. 用户管理
-------------

- 设置、取消管理员（不能对自己使用）

- 审核新用户

- 禁用用户：不允许登录、上传等一切操作

- 删除用户

- 验证过邮箱的用户邮箱字段是绿色的。

- 标签一栏允许编辑（可置空），用以设置用户分组，允许使用半角逗号分割多个标签
