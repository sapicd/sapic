.. _picbed-api:

============
RESTful API
============

**约定：**

- API返回均为JSON，除了api.index接口返回的字符串，其他都是对象，基本字段code、msg。

  code值为number，0表示处理成功，否则失败，此时msg有错误消息。

  API返回的msg支持中英文，它检测Accept-Language头或cookie的locale字段，zh-CN则返回中文。

  API返回的基本字段可以修改，可以用下面三个查询参数修改返回的基本格式：

  - status_name规定数据状态的字段名称，默认code
  
  - ok_code规定成功的状态码，默认0，ok_code=bool则会返回布尔类型，其他值均认为是number类型
  
  - msg_name规定状态信息的字段名称，默认msg

  .. code-block:: bash

    $ curl "http://127.0.0.1/api/xx?status_name=status&ok_code=200"
    - 请求成功
        {"status": 200, "msg": null}
    - 请求失败
        {"status": -1, "msg": "errmessage"}

    $ curl "http://127.0.0.1/api/xx?status_name=success&ok_code=bool&msg_name=message"
    - 请求成功
        {"success": true, "message": null}
    - 请求失败
        {"success": false, "message": "errmessage"}

    $ curl "http://127.0.0.1:9514/api/xx?ok_code=abc"
    - ok_code不是number类型或bool值，则一律返回默认
    {"code": 0, "msg": null}

- API返回的响应头可能有以下两个公共字段。

  - 当内置Token钩子开启后

    Access-Control-Allow-Headers: Authorization

  - 当管理员在控制台CORS-Origin设置后
  
    Access-Control-Allow-Origin: \*或具体来源

- API返回非200状态码时，404、405、413、500都返回JSON基本格式，msg是状态码名字

- 以下接口要求boolean类型的，值可以是true、True、1、on、yes, 均认为是真，反之则假！

- 以下接口，顶部的 ``api.xxx`` 这部分就叫端点，endpoint，下面是普通用户可能用到的。

1. api.index
-------------

.. http:any:: /api/, /api/index

  Api首页，仅用来表明登录态，允许 :http:method:`post` :http:method:`get` 方法

  返回: Hello picbed(未登录)/<username>(已登录)

2. api.login
-------------

.. http:post:: /api/login
  
  登录接口

  :form username: 用户名
  :form password: 登录密码
  :form set_state: boolean: 是否设置登录态
  :form remember: boolean: 是否记住我(7d)
  :resjson string sid: SessionId
  :resjson string expire: 过期时间戳

  **示例：**

  .. http:example:: curl python-requests

    POST /api/login HTTP/1.0
    Host: 127.0.0.1:9514
    Content-Type: application/x-www-form-urlencoded

    username=xxx&&password=your-password-here


    HTTP/1.0 200 OK
    Content-Type: application/json

    {
        "code": 0,
        "sid": "xxxxxxx",
        "expire": 123456789
    }


3. api.register
-----------------

.. http:post:: /api/register
  
  注册接口

  :form username: 用户名
  :form password: 密码
  :form avatar: 头像地址
  :form nickname: 昵称
  :statuscode 404: 管理员关闭注册时

  **示例：**

  .. http:example:: curl python-requests

    POST /api/register HTTP/1.0
    Host: 127.0.0.1:9514
    Content-Type: application/x-www-form-urlencoded

    username=xxx&&password=your-password-here


    HTTP/1.0 200 OK
    Content-Type: application/json

    {
        "code": 0
    }

4. api.waterfall
-----------------

.. http:get:: /api/waterfall
  
  图片列表接口，要求登录，也允许 :http:method:`post` 方法查询。

  :query string sort: 根据图片上传时间排序，asc正序，desc倒序
  :query number page: 页数，从1开始
  :query number limit: 一次性返回条数，默认10
  :query boolean is_mgr: 要求以管理员级别查询（当然用户也得是管理员才行）
  :query string album: 查询相册，可以用逗号分隔查询多个相册
  :form album: 等于query查询参数的album
  :resjson number count: 用户的图片总数
  :resjson number pageCount: 根据limit和count计算的总页数
  :resjsonarr albums: 用户的相册列表 
  :resjsonarr data: 用户的图片列表（其中字段参考shamgr接口）
  :statuscode 403: 未登录时

  **示例：**

  .. http:example:: curl python-requests

    GET /api/waterfall HTTP/1.0
    Host: 127.0.0.1:9514
    Authorization: LinkToken Your-LinkToken-Value

    :query limit: 1


    HTTP/1.0 200 OK
    Content-Type: application/json

    {
        "albums": [
            "misc",
            "gif",
            "test",
            "LinkPlugin"
        ],
        "code": 0,
        "count": 57,
        "data": [
            {
                "agent": "homepage/0.5.5",
                "album": "",
                "ctime": 1589266897,
                "filename": "1589266897617.gif",
                "sender": "up2local",
                "senders": [
                    {
                        "code": 0,
                        "sender": "up2local",
                        "src": "http://127.0.0.1:9514/static/upload/admin/1589266897617.gif"
                    }
                ],
                "sha": "sha1.1589266897.6169922.80b939eca2183d30281bfdc29ba41aac8f8a21ed",
                "src": "http://127.0.0.1:9514/static/upload/admin/1589266897617.gif",
                "status": "enabled",
                "upload_path": "admin/",
                "user": "admin"
            }
        ],
        "msg": null,
        "pageCount": 57
    }


5. api.shamgr
-----------------

.. http:get:: /api/shamgr/<string:sha>
  
  图片详情接口

  :param sha: 图片的唯一标识
  :type sha: string
  :resjson object data: 图片详情（上述接口的图片列表中包含的就是此详情数据）
  :resjson album: 相册（当前及下方字段位于data内）
  :resjson src: 图片在picbed中的链接
  :resjson sender: 图片保存者（钩子名）
  :resjson object tpl: URL文本复制的模板
  :resjson agent: 上传来源UserAgent
  :resjson filename: 最终保存到服务器文件名
  :resjson sha: 图片唯一标识
  :resjson status: 状态
  :resjson user: 所属用户
  :resjson upload_path: 图片前缀路径
  :statuscode 404: 没有对应图片时

  **示例：**

  .. http:example:: curl python-requests

    GET /api/shamgr/sha1.xxxxxxx HTTP/1.0
    Host: 127.0.0.1:9514


    HTTP/1.0 200 OK
    Content-Type: application/json

    {
        "code": 0,
        "data": {
            "album": "",
            "src": "http://127.0.0.1:9514/static/upload/admin/1589266897617.gif",
            "sender": "up2local",
            "tpl": {
                "URL": "http://127.0.0.1:9514/static/upload/admin/1589266897617.gif",
                "rST": ".. image:: http://127.0.0.1:9514/static/upload/admin/1589266897617.gif",
                "HTML": "<img src='http://127.0.0.1:9514/static/upload/admin/1589266897617.gif' alt='1589266897617.gif'>",
                "Markdown": "![1589266897617.gif](http://127.0.0.1:9514/static/upload/admin/1589266897617.gif)"
            },
            "agent": "homepage/0.5.5",
            "filename": "1589266897617.gif",
            "sha": "sha1.1589266897.6169922.80b939eca2183d30281bfdc29ba41aac8f8a21ed",
            "status": "enabled",
            "user": "admin",
            "upload_path": "admin/",
            "senders": null,
            "ctime": 1589266897
        }
    }

.. http:delete:: /api/shamgr/<string:sha>

  图片删除接口，要求登录，只有图片所属用户和管理员允许删除。

  :param sha: 图片的唯一标识
  :type sha: string
  :statuscode 404: 没有对应图片时
  :statuscode 403: 未登录或图片所属用户与请求用户不匹配

  **示例：**

  .. http:example:: curl python-requests

    DELETE /api/shamgr/sha1.xxxxxxx HTTP/1.0
    Host: 127.0.0.1:9514
    Authorization: LinkToken Your-LinkToken-Value

.. http:put:: /api/shamgr/<string:sha>

  图片数据更新接口，要求登录，只有图片所属用户和管理员允许修改。

  :param sha: 图片的唯一标识
  :type sha: string
  :query string Action: 更新指令，目前仅支持一个updateAlbum（更新相册名）
  :form album: 相册名
  :statuscode 404: 没有对应图片时
  :statuscode 403: 未登录或图片所属用户与请求用户不匹配

  **示例：**

  .. http:example:: curl python-requests

    PUT /api/shamgr/sha1.xxxxxxx HTTP/1.0
    Host: 127.0.0.1:9514
    Authorization: LinkToken Your-LinkToken-Value

    :query Action: updateAlbum

    album=newName


6. api.album
-----------------

.. http:get:: /api/album
  
  用户相册列表接口，要求登录，也允许 :http:method:`post` 方法查询。

  :resjsonarr data: 相册列表
  :resjson object counter: 每个相册中的图片数

  **示例：**

  .. http:example:: curl python-requests

    GET /api/album HTTP/1.0
    Host: 127.0.0.1:9514
    Authorization: LinkToken Your-LinkToken-Value


    HTTP/1.0 200 OK
    Content-Type: application/json

    {
        "msg": null,
        "code": 0,
        "data": [
            "misc",
            "gif",
            "test",
            "LinkPlugin"
        ],
        "counter": {
            "misc": 1,
            "gif": 1,
            "test": 7,
            "aaaaa": 1,
            "LinkPlugin": 2
        }
    }

.. _picbed-api-upload:

7. api.upload
-----------------

.. http:post:: /api/upload
  
  图片上传接口，默认不允许匿名（可由管理员开启允许），有两种上传方式，
  文件域表单和base64。

  .. versionchanged:: 1.2.0

    v1.2.0新增一种图片链接上传（目前共三种上传方式），picbed字段值为URL形式时，
    会尝试下载图片（URL符合规则且下载的确实是图片类型才能成功）。

    上传方式优先级：文件域 > Image URL > Image base64

  获取上传数据的字段默认是picbed，管理员可以在控制台修改，但是不建议改，
  如果要改，首页上传会自动更新，但引用uploader.js在外部上传的话，那就需要
  设置 **name** 值，具体参考 :ref:`LinkToken-upload-plugin` ，有一个name选项
  可以设置其他值。

  :query string format: 指定图片地址的显示字段
  :form format: 等于query查询参数的format
  :form album: 图片所属相册（匿名时总是直接设置为anonymous）
  :form picbed: 上传字段名
  :form filename: 使用 **base64/url** 方式上传时此值有效，设定文件名
  :resjson string filename: 最终保存到服务器的文件名
  :resjson string sender: 保存图片的钩子名
  :resjson string api: 图片详情接口的地址 
  :resjson string src: 图片地址
  :statuscode 403: 管理员不允许匿名上传且用户未登录时

  .. tip::

    - 当接口获取不到文件时，判断picbed字段值，如果以http://或https://开头，
      那么进入Image URL上传流程，否则进入Image Base64上传流程。

    - Image URL上传，程序会从url中尝试查找出文件名，无效时判定失败，除非手动设置文件名。
      
      .. versionchanged:: 1.4.0

        优化了图片链接上传，程序自动尝试从链接查找文件名，无果也无妨，
        继续请求url，根据其返回内容、类型猜测文件后缀。
      
      程序使用get方式请求url，只有返回状态码是2xx或3xx且Content-Type是image
      类型时才有效。

      简而言之，是真正的图片链接才行。当然，被伪造也是可能的。

    - base64方式上传允许 `Data URI <https://developer.mozilla.org/docs/Web/HTTP/data_URIs>`_ 形式的！

    - 图片地址src是可以自定义的，利用format参数，允许使用最多一个点号。

      举例，默认返回{code:0, src:xx}

      - format=imgUrl  （这种情况最少需要两个字符）

        {code:0, imgUrl:xx}

      - format=data.src

        {code:0, data:{src:xx}}

      大概是这两种情况，src字段改名或者改为子对象中的字段。

      再结合顶部约定处的公共查询参数自定义返回的基本字段，此处src定制灵活度
      很高。

  .. note::
  
    上传流程：

    1. 登录及匿名上传判断

    2. 获取文件（三种方式）

    3. 如果文件有效，初始化相关参数，交给上传类钩子处理图片流并回传结果进行后续处理

    4. 返回响应数据

  **请求与响应示例：**

  .. http:example::

    POST /api/upload HTTP/1.0
    Host: 127.0.0.1:9514
    Authorization: LinkToken Your-LinkToken-Value


    HTTP/1.0 200 OK
    Content-Type: application/json

    {
        "src": "http://127.0.0.1:9514/static/upload/admin/1589362171435.jpg",
        "code": 0,
        "sender": "up2local",
        "filename": "1589362171435.jpg",
        "api": "http://127.0.0.1:9514/api/sha/sha1.1589362171.44.790d07c9a0fd7538ea9dc7c1ec208dbcd291ce35",
        "msg": null
    }

  **文件域上传示例：**

  - curl

    .. code-block:: bash

        $ curl -H "Authorization: LinkToken xxxx" -XPOST \
          http://127.0.0.1:9514/api/upload -F "picbed=@上传的图片路径"

  - python

    .. code-block:: python

        files = {
            'picbed': (filename, open("图片", "rb"))
        }
        headers = {"Authorization": "LinkToken xxxx"}
        requests.post(
            "http://127.0.0.1:9514/api/upload",
            files=files,
            headers=headers,
        ).json()


  **Image Base64上传示例：**

  - curl

    .. code-block:: bash

        $ curl -H "Authorization: LinkToken xxxx" -XPOST \
          http://127.0.0.1:9514/api/upload -d picbed="图片base64编码" -d filename="test.jpg"

  - python

    .. code-block:: python

        headers = {"Authorization": "LinkToken xxxx"}
        requests.post(
            "http://127.0.0.1:9514/api/upload",
            data=dict(
                picbed="data:image/jpg;base64,图片base64编码"
            ),
            headers=headers,
        ).json()

  - ajax

    .. code-block:: javascript

        $.ajax({
            url: 'http://127.0.0.1:9514/api/upload',
            method:'POST',
            data: {picbed: 'data:image/png;base64,图片base64编码'},
            success:function(res){
                console.log(res);
            }
        });

  **Image URL上传示例：**

  - curl

    .. code-block:: bash

        $ url=https://hbimg.huabanimg.com/6b7b7456a3cb7b1b149be2463dca29c18e8c03c2bd0c-DcxKZ5
        $ curl -XPOST -H "Authorization: LinkToken xxxx" \
          http://127.0.0.1:9514/api/upload -d picbed="${url}"
        {
            "code": 0
            "src": "xxx",
            "filename": "xx",
            "sender": "up2local"
        }

  - python

    .. code-block:: python

        headers = {"Authorization": "LinkToken xxxx"}
        requests.post(
            "http://127.0.0.1:9514/api/upload",
            data=dict(
                picbed="https://xxxx.com/your-image.png"
            ),
            headers=headers,
        ).json()

8. api.my
-----------

  修改用户资料、密码等

9. api.ep
----------

  专为钩子实现的接口

10. api.link
--------------

  LinkToken管理接口

11. api.report
---------------

  记录查询接口

