.. _picbed-install:

===========
部署安装
===========

.. note::

    部署就是三步走，一步准备工作，一步安装依赖，一步配置运行。
    以下文档基于Linux的CentOS7，Ubuntu18

--------------

源码地址： https://github.com/staugur/picbed

正式版本： https://github.com/staugur/picbed/releases

内容说明： 以下部署文档适用于有一点linux基础的同学，大概涉及到yum、git、docker等命令，以及redis、nginx等服务。

.. _picbed-install-no1:

**NO.1 启动Redis**
-------------------

部署redis很简单，CentOS用户可以\ ``yum install redis``\ ，Ubuntu用户可以\ ``apt-get install redis-server``\ ，都可以编译安装，给一个教程链接：\ http://www.runoob.com/redis/redis-install.html

也可以docker启动，用官方镜像启动一个docker redis，镜像：\ https://hub.docker.com/_/redis\ 。

.. warning::

    一定记得修改redis配置文件，开启密码和AOF持久化，否则有被入侵和数据丢失风险。

.. tip::

    v1.6.0及之后版本兼容了redis cluster集群模式，可以将数据存到集群中，
    具体参考配置。

.. _picbed-install-no2:

**NO.2 部署程序**
---------------------

这是一个基于Python Flask框架写的web应用，依赖redis，部署要求python2.7、3.5+

.. note::

    目前测试了CentOS、Ubuntu的py2.7、3.5、3.6、pypy、pypy3版本。

2.1. 下载源码
^^^^^^^^^^^^^^^

- 开发版

    ! 建议，如果你有git，可以：\ ``git clone https://github.com/staugur/picbed``

    ! 也可以下载压缩包：

    .. code-block:: bash

        $ wget -O picbed.zip https://codeload.github.com/staugur/picbed/zip/master
        $ unzip picbed.zip 
        $ mv picbed-master picbed

- 正式版

    ! 到 `release <https://github.com/staugur/picbed/releases>`_ 页面下载正式版本的包。

2.2 安装依赖
^^^^^^^^^^^^^^

.. code-block:: bash

    $ git clone https://github.com/staugur/picbed
    $ cd picbed
    $ [建议]激活virtualenv、venv，或者直接在全局模式下安装
    $ pip install -r requirements/all.txt # all可以换成具体env

.. versionchanged:: 1.1.0

    requirements目录是依赖包文件所在，env是环境，比如开发环境是dev，正式环境是prod。

    .. code-block:: bash

        $ pip install -r requirements/dev.txt
    
    在v1.1.0+版本内置了几个对象存储钩子，需要安装的模块在此目录下以 *up2xxx.txt* 命名，
    你在控制台开启使用了某个钩子就需要安装对应模块，比如开启又拍云上传，请先安装：

    .. code-block:: bash

        $ pip install -r requirements/up2upyun.txt

    当然，也可以直接全部安装：

    .. code-block:: bash

        $ pip install -r requirements/all.txt

requirements目录几个txt文件，up2xxx都是独立的，dev/prod依赖基础的base.txt，
而终极大法就是all.txt，直接安装了所有依赖。

.. _picbed-config:

2.3 修改配置
^^^^^^^^^^^^^^

配置文件是源码src目录下的config.py，它会加载同级目录 **.cfg** 文件读取配置信息，
无法找到时再加载环境变量，最后使用默认值，必需的配置项是picbed_redis_url。

所以可以把配置项写到 `.bash_profile` 或 `.bashrc` 此类文件中在登录时加载，
也可以写入到 `.cfg` 文件里，这是推荐的方式，它不会被提交到仓库，格式是k=v，
每行一条，注意，v是所见即所得！

比如: `picbed_redis_url=redis://@localhost`

可设置列表如下：

================  ==========================  ===============   ====================================================================
    配置              [环境]变量名                默认值                                       说明
================  ==========================  ===============   ====================================================================
HOST              picbed_host                 127.0.0.1         监听地址
PORT              picbed_port                  9514             监听端口
LOGLEVEL          picbed_loglevel              DEBUG            日志级别，可选DEBUG, INFO, WARNING, ERROR, CRITICAL
SecretKey         picbed_secretkey             无               App应用秘钥(默认自动生成)
**REDIS**         picbed_redis_url             无               核心数据存储（redis连接串，格式是：redis://[:password]@host:port/db）
================  ==========================  ===============   ====================================================================

更多参数请参考config.py配置文件中的注释。

!!!以上参数 **REDIS** 无默认值，必须根据实际情况手动设置，
示例如下（可以写入.bash\_profile中）：

.. code-block:: bash

    $ export picbed_redis_url="redis://:password@127.0.0.1:6379/1"
    或者
    $ cat .cfg
    picbed_redis_url=redis://:password@127.0.0.1:6379/1

.. versionchanged:: 1.6.0

    v1.6.0支持redis cluster集群连接，格式：``rediscluster://host:port,host:port...``
    其他地方无需修改，暂不支持密码

2.4 启动程序
^^^^^^^^^^^^^^

开发环境::

    $ make dev

正式环境::

    $ sh online_gunicorn.sh start  #可以用run参数前台启动，status查看状态，stop停止，restart重启，reload重载

    或者使用make start等同于上述命令，其他诸如: make stop, make restart, makre load, make status

.. tip::

    部署程序可以使用Docker，源码中已经写好了Dockerfile，您可以藉此构建或者
    使用构建好的 `staugur/docker <https://hub.docker.com/r/staugur/picbed>`_ ，
    详情请看 :ref:`picbed-docker-deploy`

**NO.3 Nginx配置**
-------------------

在程序启动后，默认情况下，监听地址是127.0.0.1:9514

Nginx配置示例如下，您也可以配置使其支持HTTPS:

.. code-block:: nginx

    server {
        listen 80;
        server_name 域名;
        charset utf-8;
        #防止在IE9、Chrome和Safari中的MIME类型混淆攻击
        add_header X-Content-Type-Options nosniff;
        #上传大小限制12M（实际程序上限是10M）
        client_max_body_size 12M;
        #可以设置不允许搜索引擎抓取信息
        #处理静态资源，root路径根据实际情况修改
        location ~ ^\/static\/.*$ {
            root /path/to/picbed/src/;
        }
        location / {
            #9514是默认端口，根据实际情况修改
            proxy_pass http://127.0.0.1:9514;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }
    }

程序部署好+Nginx配置完成，启动后，这个域名就能对外服务了（温馨提示：您可以使用HTTPS提供服务，并且也建议用HTTPS），即可进入下一篇查看如何注册、使用。

**NO.4 演示站**
-------------------

目前在国内部署了一个演示站，使用master最新代码测试新功能，服务地址是：

    http://picbed.demo.saintic.com

    测试账号及密码：demo 123456

由于开启匿名上传出现大量“不适”图片，所以关闭了匿名，可以注册测试，也可以
使用上述测试账号，请不要修改其密码。

另请勿将其当做永久站，图片不定时删除，仅作测试演示使用。

**NO.5 程序升级**
------------------

目前git下载可以使用git pull拉取最新代码，重载或重启主程序(make reload/restart)即完成升级。

.. tip::

    reload/restart在大部分情况下都可以重载代码和配置(从.cfg读取)，但是如果
    需要从环境变量重新读取配置，那么只能用restart。

下面提到的版本在升级时需要注意，未提及的直接更新代码和程序即可。

- v1.2.0

    增加了依赖，需要安装requests模块（pip install requests），
    已写到requirements/base.txt

- v1.6.0

    1. 兼容了redis cluster集群模式，如果使用此存储，需要安装redis-py-cluster模块

    .. code-block:: bash
    
        $ pip install redis-py-cluster>1.0.0
    
    此依赖已写到requirements/optional.txt文件中

    2. LinkToken统计功能设计更改
    
    旧版本调用统计写入到redis的 `picbed:report:linktokens` 中，此版本改为
    `picbed:report:linktokens:{username}`

    如果需要旧数据，可以将旧版key改名，加上 `:{your username}`
