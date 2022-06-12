sapic - 简约不小气的自建图床程序
====================================

.. toctree::
    :maxdepth: 1

    install
    docker
    usage
    linktoken
    cli
    admin
    hook
    api
    module
    faq
    changelog

.. _picbed-readme:

======
概述
======

.. image:: /_static/images/sapic.png

自 v1.12.0 正式命名：**sapic**

基于Flask的Web自建图床，默认存储在本地，
内置支持又拍云、七牛云、阿里云OSS、腾讯云COS、S3等对象存储，支持GitHub、Gitee（码云）。

GitHub： `sapicd/sapic <https://github.com/sapicd/sapic>`_

Gitee： `staugur/picbed <https://gitee.com/staugur/picbed>`_

语言：Python

框架：Flask

.. note::

    关于名称那些事：

    一开始没想好如何给这个自建图床命名，索性就直接用 picbed 了，但这个有“统称”的意思，
    有时候难以“特指”某个开源项目，在搜索、查询方面会让人模糊、诧异。

    大概在 1.10 - 1.11 版本之间，我准备用 Vue.js + ElementUI 重构前端（和后端），即
    2.0，为此准备了 **sapic** 这个名称，其含义就是 *SA Picbed* ，SA表示系统管理员。

    如今先改成sapic，更新搜索引擎记录，顺道，把相关项目也迁移到了GitHub组命名空间下：
    `sapicd <https://github.com/sapicd>`_

    要问的话，就是个人账号下有很多 picbed-xxx 扩展项目感觉碍事，而且sapic被注册，
    所以加了个d，表示“的” --- ^_^

    本次仅为项目正式命名，仅更改进程名、对外显示名和git源码地址，不变更文档地址，
    不更改配置字段，不更改Docker镜像名和内部目录结构！

    已逐步更新配置字段，镜像同时支持sapic，请查看后续文档了解详情。

    建议：普通环境使用python3.7+，Docker使用staugur/sapic镜像，配置使用sapic字样。

.. _picbed-features:

功能：
------

1. 可作为私有或公共（多用户）的图床程序

2. 可插拔的钩子管理器，允许第三方扩展功能点

  - 扩展了如sm.ms,superbed.cn等公共图床
  - 多个扩展点，针对多个功能增强，开发简单

3. API

  - 基于api的上传接口，支持通过文件域、base64（允许Data URI形式）、URL上传
  - 可定制的api响应数据[及字段]及中英错误消息提示
  - 支持Token以及更安全的基于Token的LinkToken调用api
  - 外部网站通过按钮一键上传的插件

4. 我的图片快捷复制支持原生URL、HTML、reStructuredText、Markdown格式，可定制图片处理

5. 管理员控制台可配置全局参数定制站点信息以及用户个性自定义覆盖全局参数

6. 支持PyPy、Python2.7、3.6+（强烈推荐），支持Docker且实时构建最新镜像传到官方仓库

7. 支持油猴脚本（用户脚本） ，使用它，几乎可以采集全网图片！

8. 多种上传方式：用户脚本、JS SDK、命令行工具（支持三端系统，可集成Windows、macOS右键菜单）、支持HTTP API的图床客户端

9. 支持上传与显示、播放视频

不足：
-------

- 图床管理暂时不能批量化；

- 基于redis的数据存储，虽响应快，但数据存储方面可能有些风险，请注意持久化及备份数据！

.. _picbed-deploy:

一句话部署：
------------

1. 要求： Python2.7（3.6+，推荐，PyPy、PyPy3）和Redis
2. 下载： ``git clone https://github.com/sapicd/sapic && cd sapic``
3. 依赖： ``pip install -r requirements/all.txt``
4. 配置： ``config.py`` 即配置文件，可从 `.cfg` 文件或环境变量读取配置信息。
5. 启动： make start 或 sh online\_gunicorn.sh start

详细部署请看下一篇！
--------------------

文档中录制了一些操作过程，所用系统CentOS7.8最小化安装的纯净系统，Python2.7.5
