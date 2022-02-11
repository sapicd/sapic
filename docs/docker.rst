.. _picbed-docker-deploy:

=================
使用Docker部署
=================

Dockerfile仅包含源码及其依赖的Python模块，不包含redis和nginx环境。

.. note::

    您仍需要准备好redis环境，可以参考 :ref:`picbed-install-no1`

    Docker部署有两种方法，一是使用开发者打包的镜像(就称之为官方镜像)，二是自己打包。

--------------

.. _picbed-official-image:

1. 官方镜像
=================

-  镜像地址：`dockerhub@staugur/sapic <https://hub.docker.com/r/staugur/sapic>`_

  位于Docker官方仓库，可以点击查看公开信息。

  之前镜像名是 `staugur/picbed`，v1.13同时增加了镜像 `staugur/sapic`

-  master分支即latest，dev分支标签是dev，其他已发布版本其版本号即标签

  这是利用了dockerhub在提交代码后自动构建镜像并上传，所以latest总是构建
  master分支，dev标签构建dev分支，而其他tag则是已发布版本的代码。

  拉取master分支（尝鲜版）镜像： `docker pull staugur/sapic`

  拉取dev分支（开发版）镜像： `docker pull staugur/sapic:dev`

  拉取v1.13.0镜像： `docker pull staugur/sapic:1.13.0`

.. _picbed-self-build:

2. 自行打包
=================

v1.4.0增加了Dockerfile文件，它使用alpine3.11 + python3.6，构建完成大概290M。

.. versionchanged:: 1.6.0

    重写了Dockerfile，采用分阶段构建，最终打包150M左右。

.. versionchanged:: 1.8.0

    更新清减部分依赖，目前构建完成105M左右。
    
.. versionchanged:: 1.8.1

    由于依赖的python基础镜像精简，目前构建完成仅75M左右（非压缩情况）。

打包步骤如下：

  .. code-block:: bash

    $ git clone https://github.com/sapicd/sapic && cd sapic
    $ docker build -t staugur/sapic .

构建镜像支持一个ARG：PIPMIRROR，用以指定pip源（默认是官方源），比如在国内使用清华源：

  .. code-block:: bash

    $ docker build -t staugur/sapic . --build-arg PIPMIRROR=https://pypi.tuna.tsinghua.edu.cn/simple

.. tip::

    由于Dockerfile安装了所有依赖（包括本地禁用的扩展依赖），但实际上可能用
    不着所有，故可以修改Dockerfile的 `pip install` 部分，仅安装/requirements/prod.txt

3. 启动运行
=================

3.1 单独启动
~~~~~~~~~~~~~~~~

.. code-block:: bash

    $ docker run -d --name sapic --net=host --restart=always \
        -e sapic_redis_url=redis://xxx staugur/sapic

这大概是最小的配置了，使用了宿主机网络，监听 `0.0.0.0:9514` ，sapic要求的
配置必需有sapic_redis_url，设置redis连接信息。
其他的可选配置请参考 :ref:`picbed-config` 自行设置环境变量。

查看我录制的使用docker单独启动的gif图: `picbed-alone-docker.gif <https://static.saintic.com/picbed/staugur/2020/07/24/picbed-alone-docker.gif>`_ 

.. tip::

    可以将容器中的/picbed/static/upload、/picbed/logs挂载到宿主机或数据卷，
    前者是本地方式上传图片的保存目录，后者是日志。

    示例：把容器内的静态资源（/picbed/static）挂载到数据卷picbed_static中，
    把上传目录挂载到宿主机 ``/data/picbed`` 目录上，
    如此宿主机的nginx可以直接访问了。

    .. code-block:: bash

        $ docker volume create picbed_static
        $ docker run -d --name sapic --net=host --restart=always \
            -e sapic_redis_url=redis://xxxx \
            -v picbed_static:/picbed/static \
            -v /data/picbed:/picbed/static/upload \
            staugur/sapic

    不过需要注意的是，数据卷持久化存储，后面如果更新了容器（静态资源）并
    不会更新宿主机的，所以如果重新启动容器（升级版本或更新代码后），建议
    先删除数据卷：

    .. code-block:: bash

        $ docker volume rm picbed_static

    因为使用bind方式挂载了upload上传目录，所以删除数据卷并不会删除已经上传
    的图片（位于宿主机/data/picbed）！

    查看我录制的使用docker单独启动的gif图（包括数据卷和nginx）: `picbed-docker-volume.gif <https://static.saintic.com/picbed/staugur/2020/07/24/picbed-docker-volume.gif>`_ 

如果没有问题，docker ps查看其状态是Up，系统中能看到进程：

.. code-block:: bash

    $ docker ps
    CONTAINER ID        IMAGE               COMMAND                  CREATED             STATUS              PORTS               NAMES
    fa3b592f6ae5        sapic              "gunicorn app:app -c…"   2 hours ago         Up 2 hours                              sapic

    $ ps aux|grep -E "picbed|sapic"
    root   23546  -- gunicorn: master [sapic]
    root   23548  -- gunicorn: worker [sapic]
    // 以上是使用setproctitle模块设置了优雅的进程名的效果，下面是未使用效果
    root  - {gunicorn} /python /bin/gunicorn app:app -c sapicd.py
    root  - {gunicorn} /python /bin/gunicorn app:app -c sapicd.py

3.2 使用docker-compose启动
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 1.6.0

编写了一个简单docker-compose.yml，构建并启动sapic和redis，无nginx，
redis开启AOF，宿主机映射9514端口以供外部访问。

.. code-block:: bash

    $ cd sapic
    $ docker-compose up -d
    $ docker-compose ps
        Name                 Command               State           Ports         
    ---------------------------------------------------------------------------------
    sapic_redis_1    docker-entrypoint.sh redis ...   Up      6379/tcp
    sapic_webapp_1   gunicorn app:app -c sapic ...   Up      0.0.0.0:9514->9514/tcp

    $ docker-compose images
        Container     Repository      Tag      Image Id       Size  
    ------------------------------------------------------------------
    sapic_redis_1    redis           alpine   b546e82a6d0e   31.51 MB
    sapic_webapp_1   sapic_webapp   latest   1f3c98af1c3a   105.9 MB

.. versionchanged:: 1.8.0

    - 1. 增加了数据卷，把容器内部静态目录（/picbed/static）挂载到数据卷中，
      故此宿主机上nginx可以方便访问容器内静态文件了。

      **注意！** 也将upload上传目录（位于static内）挂载到 ``/data/picbed``

    - 2. 更新代码后的操作

      升级版本或更新代码后，建议先down了所有docker-compose生成的资源（主要是
      数据卷、已构建的镜像），再构建启动新容器。

      .. code-block:: bash

        $ cd sapic
        $ docker-compose build
        $ docker-compose down -v
        $ docker-compose up -d

      因为使用bind方式挂载了upload上传目录，所以删除数据卷并不会删除已经上传
      的图片（位于宿主机/data/picbed）！

      查看我录制的使用docker-compose启动的gif图: `picbed-docker-compose.gif <https://static.saintic.com/picbed/staugur/2020/07/24/picbed-docker-compose.gif>`_

.. warning::

    仓库中的 `docker-compose.yml` 并不是推荐的正式环境级别的配置文件，仅供快速体验使用，
    正式环境更建议使用独立的redis服务器，并仔细配置 `docker-compose.yml`。

4. nginx
=================

上述不论是单独启动，还是使用docker-compose启动，对外接收请求的是gunicorn，
遗憾的是，它处理静态资源性能不好，所以一般会加一层nginx。

4.1 如果使用宿主机的nginx服务
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    单独启动请按照上面小技巧中的示例，先创建数据卷再挂载数据。
    
    使用docker-compose启动，已经在配置中完成了，直接启动就好了。

    4.1.1 设置数据卷存放目录所有人有执行权（否则可能nginx 403权限拒绝）

    .. code-block:: bash

        $ chmod +x $(docker info -f '{{ .DockerRootDir }}')/volumes

    4.1.2 nginx配置

    先获取数据卷在宿主机的目录：

    .. code-block:: bash

        $ docker volume inspect -f '{{ .Mountpoint }}' picbed_static
        /var/lib/docker/volumes/picbed_static/_data

    配置示例：

    .. code-block:: nginx

        server {
            listen 80;
            server_name 域名;
            charset utf-8;
            #上传大小限制
            client_max_body_size 20M;
            #可以设置不允许搜索引擎抓取信息
            #处理静态资源，root路径根据实际情况修改
            location ^~ /static/ {
                # 上一步获取的数据卷在宿主机的目录，注意末尾/不要丢
                alias /var/lib/docker/volumes/picbed_static/_data/;
            }
            location ^~ /static/upload/ {
                # 容器内上传目录挂载到宿主机的目录，注意末尾/不要丢
                alias /data/picbed/;
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

4.2 在Docker中使用nginx服务
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

这就简单了，启动docker版nginx同样挂载数据卷和上传目录，配置参考 :ref:`picbed-nginx`

5. 后续
=================

接下来建议您看下一节使用说明，刚开始需要创建一个管理员账号的，而使用docker
第一次启动也需要，命令如下：

.. code-block:: bash

    $ docker exec -i sapic flask sa create -u 管理员账号 -p 密码 --isAdmin

如果使用docker-compose启动，命令如下：

.. code-block:: bash

    $ docker-compose exec webapp flask sa create -u 管理员账号 -p 密码 --isAdmin

其他额外选项，如昵称、头像就不说了。
