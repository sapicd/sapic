.. _picbed-install:

===========
部署安装
===========

.. note::

    部署就是三步走，一步准备工作，一步安装依赖，一步配置运行。
    以下文档基于Linux的CentOS7，Ubuntu18

--------------

源码地址： https://github.com/sapicd/sapic

正式版本： https://github.com/sapicd/sapic/releases

内容说明： 以下部署文档适用于有一点linux基础的同学，大概涉及到yum、git、docker等命令，以及redis、nginx等服务。

.. _picbed-install-no1:

NO.1 启动Redis
-------------------

部署redis很简单，版本要求2.8+、3.x、4.x，另外未测试过5.0+版本，不确保其正确性。

- CentOS/RHEL

  .. code-block:: bash

    $ sudo yum install -y epel-release
    $ sudo yum install -y redis

- Ubuntu

  .. code-block:: bash

    $ sudo apt update
    $ sudo apt-get install redis-server

- 编译安装

  .. code-block:: bash

    // version可替换为其他版本
    $ version="3.2.0"
    $ wget http://download.redis.io/releases/redis-${version}.tar.gz
    $ tar xzf redis-${version}.tar.gz
    $ cd redis-${version}
    $ make
    $ ./src/redis-server ./redis.conf # 编译成功的话此处正常启动服务了

- 或者可以docker启动，用官方镜像启动一个docker redis，地址：\ https://hub.docker.com/_/redis\ 。

.. warning::

    一定记得修改redis配置文件，开启AOF持久化，建议设置密码、只绑定本机，
    否则有被入侵和数据丢失风险。

    ps：上述内容供参考，若启动失败，请参考官方或其他文档。

.. tip::

    v1.6.0及之后版本兼容了redis cluster集群模式，可以将数据存到集群中，
    具体参考配置。

    使用redis集群，需要安装redis-py-cluster模块，它写在了可选模块文件：requirements/optional.txt

    查看我录制的安装redis的gif图: `redis-install.gif <https://static.saintic.com/picbed/staugur/2020/07/24/redis-install.gif>`_

.. _picbed-install-no2:

NO.2 部署程序
---------------------

这是一个基于Python Flask框架写的web应用，依赖redis，部署要求python2.7、3.6+，
推荐使用版本3.7及之后版本。

.. note::

    目前测试了CentOS、Ubuntu的py2.7、3.6、3.7、pypy、pypy3版本。

2.1. 下载源码
^^^^^^^^^^^^^^^

目前GitHub上保持两个分支：dev、master

dev是开发分支，不建议非开发人员使用；
dev分支的功能完成后会合并到master分支；
一阶段功能完成会从master分支发版。

- 开发版（dev）
    ! 建议，如果你有git，可以：\ ``git clone -b dev https://github.com/sapicd/sapic picbed``

    ! 也可以下载压缩包：

    .. code-block:: bash

        $ wget -O picbed.zip https://codeload.github.com/sapicd/sapic/zip/dev
        $ unzip picbed.zip 
        $ mv picbed-dev picbed

- 尝鲜版（master）
    ``git clone https://github.com/sapicd/sapic picbed``

- 正式版（release）
    ! 到 `release <https://github.com/sapicd/sapic/releases>`_ 页面下载正式版本的包。

2.2 安装依赖
^^^^^^^^^^^^^^

目前从最小化安装的CentOS7.8系统中整体部署了下，没有特殊的系统层面的依赖软件。

.. code-block:: bash

    $ cd picbed
    $ [建议]激活virtualenv、venv，当然也可以直接在全局模式下安装
    $ pip install -r requirements/all.txt # all可以换成具体env

.. versionchanged:: 1.1.0

    requirements目录是依赖包文件所在，env是环境，比如开发环境是dev，正式环境是prod。

    .. code-block:: bash

        $ pip install -r requirements/dev.txt

    在v1.1.0+版本内置了几个对象存储钩子（上传），需要安装的模块在此目录下
    以 *up2xxx.txt* 命名，你想使用某个钩子就需要安装对应模块，
    比如开启又拍云上传，请先安装：

    .. code-block:: bash

        $ pip install -r requirements/up2upyun.txt

    当然，也可以直接全部安装：

    .. code-block:: bash

        $ pip install -r requirements/all.txt

requirements目录几个txt文件，up2xxx都是独立的，dev/prod依赖基础的base.txt，
procname.txt是设置进程名的模块（非必需），docs.txt是构建文档的模块（py3+），
optional.txt是系统可选功能依赖的模块（可选）。

而终极大法就是all.txt，直接安装了prod.txt和up2xxx.txt。

.. versionchanged:: 1.8.0

    all.txt移除了procname.txt，这个是setproctitle模块，优雅地设置进程名，但是
    它所依赖gcc和python-dev包，太"重"了，所以不放到all里面了，有需要可以自己
    单独安装。

    - CentOS/RHEL
        $ sudo yum install -y gcc python-devel # python3-devel

    - Ubuntu
        $ sudo apt install build-essential python-dev # python3-dev

.. tip:: 

    如果pip install时提示命令不存在，那么可以这么安装pip：

    .. code-block:: bash

        $ curl https://bootstrap.pypa.io/get-pip.py | python

    当然，也可以使用操作系统的包管理工具，如yum、apt-get安装。

    在国内，pip可以使用清华源：

    .. code-block:: bash

        $ pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pip -U
        $ pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

.. _picbed-config:

2.3 修改配置
^^^^^^^^^^^^^^

配置文件是源码src目录下的config.py，它会加载同级目录 **.cfg** 文件读取配置信息，
无法找到时再加载环境变量，最后使用默认值，必需的配置项是sapic_redis_url。

所以可以把配置项写到 `.bash_profile` 或 `.bashrc` 此类文件中在登录时作为环境变量加载，
也可以写入到 `.cfg` 文件里（源码 src 目录下），这是推荐的方式，
它不会被提交到仓库，格式是k=v，每行一条，注意：
v是所见即所得（不要有多余的引号等，除非真的需要）！

比如: `sapic_redis_url=redis://@localhost`

可设置列表如下：

================  ==========================  ===============   ====================================================================
    配置              [环境]变量名                默认值                                       说明
================  ==========================  ===============   ====================================================================
HOST              sapic_host                  0.0.0.0           监听地址
PORT              sapic_port                  9514              监听端口
LOGLEVEL          sapic_loglevel              DEBUG             日志级别，可选DEBUG, INFO, WARNING, ERROR, CRITICAL
**REDIS**         sapic_redis_url             无                核心数据存储（redis连接串，格式是：redis://[:password]@host:port/db）
SecretKey         sapic_secretkey             (大长串)          App应用秘钥(默认有固定值)
MaxUpload         sapic_maxupload             20                设定程序最大上传容量，单位MB
ProxyFix          sapic_proxyfix              无                信任代理标头
================  ==========================  ===============   ====================================================================

更多参数请参考 config.py 配置文件中的注释。

!!!以上参数 **REDIS** 无默认值，必须根据实际情况手动设置，
示例如下（可以写入.bash\_profile中）：

.. code-block:: bash

    $ export sapic_redis_url="redis://:password@127.0.0.1:6379/1"
    或者写入文件
    $ cat .cfg
    sapic_redis_url=redis://:password@127.0.0.1:6379/1

.. versionchanged:: 1.6.0

    v1.6.0支持redis cluster集群连接，格式：``rediscluster://host:port,host:port...``
    其他地方无需修改，暂不支持密码

.. versionchanged:: 1.13.0

    配置读取环境变量时支持sapic前缀，比如picbed_host，优先读取sapic_host

.. tip:: 

    SecretKey之前是随机生成，在1.8.0设置为固定默认值，建议设置其他复杂的值！

2.4 启动程序
^^^^^^^^^^^^^^

开发环境

.. code-block:: bash

    $ cd picbed/src
    $ make dev

正式环境::

    $ cd picbed/src
    $ sh online_gunicorn.sh start  #可以用run参数前台启动，status查看状态，stop停止，restart重启，reload重载

    或者使用make start等同于上述命令，其他诸如: make stop, make restart, makre load, make status

.. tip::

    - 部署程序可以使用Docker，源码中已经写好了Dockerfile，您可以藉此构建或者
      使用构建好的 `picbed @ docker hub <https://hub.docker.com/r/staugur/picbed>`_ ，
      详情请看 :ref:`picbed-docker-deploy`

    - 刚启动的picbed是没有默认管理员用户的，需要使用命令行手动创建，
      参考 :ref:`picbed-usgae`

    - 查看我录制的手动部署的gif图: `picbed-install.gif <https://static.saintic.com/picbed/staugur/2020/07/24/picbed-install.gif>`_ 

.. _picbed-nginx:

NO.3 Nginx配置
-------------------

Nginx配置示例如下，您也可以配置使其支持HTTPS:

.. code-block:: nginx

    server {
        listen 80;
        server_name 域名;
        charset utf-8;
        #防止在IE9、Chrome和Safari中的MIME类型混淆攻击
        add_header X-Content-Type-Options nosniff;
        #上传大小限制（单位，实际程序上限默认是20M，可以手动设定上限，此处同步限制）
        client_max_body_size 20M;
        #可以设置不允许搜索引擎抓取信息
        #处理静态资源，root路径根据实际情况修改
        location ~ ^\/static\/.*$ {
            root /path/to/<程序目录>/src/;
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

此处也录制了安装配置nginx的gif图: `picbed-nginx.gif <https://static.saintic.com/picbed/staugur/2020/07/24/picbed-nginx.gif>`_

NO.4 演示站
-------------------

目前在国内部署了一个演示站，使用最新代码测试新功能，服务地址是：

    http://demo.sapicd.com

    测试账号及密码：demo 123456

由于开启匿名上传出现大量“不适”图片，所以关闭了匿名，可以注册测试，也可以
使用上述测试账号，请不要修改其密码。

另请勿将其当做永久站，图片不定时删除，仅作测试演示使用。

.. _picbed-upgrade:

NO.5 程序升级
------------------

目前git下载可以使用git pull拉取最新代码，重载或重启主程序(make reload/restart)即完成升级。

.. tip::

    reload/restart在大部分情况下都可以重载代码和配置(从.cfg读取)，但是如果
    需要从环境变量重新读取配置，那么只能用restart。

下面提到的版本在升级时需要注意，未提及的直接更新代码和程序即可。

从旧版本跨多个版本更新，在拉取最新代码后，参考下面升级到对应版本的注意事项，
如果使用upgrade命令行，注意不要跨版本（当然其参数固定，也无法跨多个）。

- v1.2.0
    增加了依赖，需要安装requests模块（pip install requests），
    已写到requirements/base.txt

- v1.6.0
    1. 兼容了redis cluster集群模式，如果使用此存储，需要安装redis-py-cluster模块

    .. code-block:: bash
    
        $ pip install redis-py-cluster>1.0.0
    
    此依赖已写到requirements/optional.txt文件中

    1. LinkToken统计功能设计更改
    
    旧版本调用统计写入到redis的 `picbed:report:linktokens` 中，此版本改为
    `picbed:report:linktokens:{username}`

    如果需要旧数据，可以将旧版key改名，加上 `:{your username}`

- v1.7.0
    值得一提的是，这个版本命令行增加了upgrade子命令，用来在版本更新时迁移数据、字段等。

    .. code-block:: bash

        $ cd picbed/src
        $ flask sa upgrade -h
        Usage: flask sa upgrade [OPTIONS] [1.6-1.7]

        版本升级助手

        Options:
            --yes       Confirm the action without prompting.
            -h, --help  Show this message and exit.

    所以，从1.6升级代码到1.7，请执行命令（可以多次执行）：

    .. code-block:: bash

        $ cd picbed/src
        $ flask sa upgrade --yes 1.6-1.7

- v1.8.0
    - 增加了依赖模块bleach和semver，可以手动安装：
    
      .. code-block:: bash
      
        $ pip install 'bleach>2.0.0' 'semver>=2.9.1,<3'

    - 更改设计：已删除图片的数据直接删除，故此升级时可以清理历史遗留的key

    以上都可以通过命令行自动完成：

    .. code-block:: bash

        $ cd picbed/src
        $ flask sa upgrade --yes 1.7-1.8

    .. warning::

        up2cos、up2oss两个钩子从内置移除了，独立成第三方，分别是：
        `staugur/picbed-up2cos <https://github.com/sapicd/up2cos>`_ 、
        `staugur/picbed-up2oss <https://github.com/sapicd/up2oss>`_

