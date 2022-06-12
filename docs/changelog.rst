.. _picbed-changelog:

=========
更新日志
=========

v1.13.6
--------

Released in 2022-06-12

- 修订模块版本问题（PS：请使用 Python3 部署，即将废弃 Python2 支持）

v1.13.5
--------

Released in 2022-06-12

- 更新文档
- 图片显示增加 alt 参数以修复破损无法正常显示时 Chrome 无法点击问题

v1.13.4
--------

Released in 2022-01-15

- uploader.js set version 1.2.0, update style

v1.13.3
--------

Released in 2021-10-24

- fix control page `upload_include` 500 error
- update ICP link address
- update docs picbed to sapic

v1.13.2
--------

Released in 2021-09-04

- fix: nginx -> docker(https/http)
- chore: build docker image with amd64 and arm64
- chore: format and update userscript
- chore: change config: host(127.0.0.1 to 0.0.0.0)
- chore: dockerfile add `EXPOSE`

v1.13.1
--------

Released in 2021-05-16

fix: api load video compatible

v1.13.0
--------

Released in 2021-05-15

功能：
  - 管理员控制台 `Ctrl/Command + S` 快捷键保存配置
  - 关于本站：公开了部分公共信息
  - 上传字段用户可由 `_upload_field` 自行指定。
  - 上传视频功能（及周边兼容），api、cli、homepage均支持

优化：
  - 上传大小限制，后端接口实现

更改：
  - 部分picbed字样更改为sapic
    - 更新文档
    - 更新hook
    - 配置读取环境变量时兼容sapic前缀
    - docker镜像同时上传 staugur/picbed 和 staugur/sapic
  - cli客户端命令行工具兼容

修复：
  - 尝试性修复 nginx with docker 模式下 local 生成 https url 问题（感谢@Nestle）

v1.12.0
--------

Released in 2021-01-20

.. image:: /_static/images/sapic.png

项目正式命名为 **sapic**

功能：
  - 图片覆盖上传

  - 按照用户label设置上传图片限制

优化：
  - 用户设置label时允许多个label

  - 显示图片信息时优化sha，增加复制

更改：
  - CICD由 Travis-CI 改为 GitHub Actions

  - 文档/源码适应正式名称的大更新！
  
    - 程序进程名更改为sapic，进程配置文件改为sapicd.py

    - api.index显示hello picbed(未登录时)改为hello sapic

    - 源码仓库统一放入 `sapicd <https://github.com/sapicd>`_ 组织中

    - picbed-cli命令行客户端发布新版v0.5.0，可执行程序名改为 **sapicli**

v1.11.0
--------

Released in 2020-12-15

功能：
  - 命令行客户端更新：

    - cli.py win10 通知功能
    - emmmm, 然后cli.py就被废弃，全部功能用golang重写，命名为
      `picbed-cli <https://github.com/sapicd/cli>`_
    - 命令行文档更新，cli.py文档仍然保留

  - 图片分享功能

  - 管理员控制台新增"注册审核邮箱"，开启注册审核并填写审核邮箱后，新用户注册会发送邮件提醒，
    不过发送邮件依赖邮件服务。

  - 新用户注册审核结果通知：无论拒绝还是通过，前提是用户验证了邮箱。
    另外，发送邮件也依赖邮件服务。

更改：
  - 配合picbed-cli，api返回的msg字段None改为空字符串
  - LinkToken统计的UserAgent解析picbed-cli专属头字段并进行图标显示

v1.10.5
-------

Released in 2020-11-07

- api.upload返回字段增加tpl：url、md、rst、html模板

- cli.py增加上传后复制，支持win/mac/可选tpl模板类型

v1.10.4
-------

修复钩子管理器删除第三方钩子时存在钩子名与模块名不一致时删除失败的问题

v1.10.3
-------

优化Feed Rss标题名

v1.10.2
-------

修复注册页面密码校验

v1.10.1
-------

Released in 2020-09-03

功能：
  - Layui页面封装了一个简洁美观的消息通知模块 **message**
  - 通过 :func:`utils.web.push_user_msg` 推送给用户消息
  - 支持用户自行删除账号
  - 支持导入网络图片 :ref:`api.load <picbed-api-load>`
  - 用户上传图片支持设置默认相册
  - 用户个人图片的RSS Feed
  - :ref:`misc/cli.py <picbed-command-line>` 输出风格支持编写函数以定制输出
  - js sdk(uploader.js)支持title并取消上传容量限制

修复：
  - 多线程下管理员控制台加载钩子扩展时常出现的数据不足的问题

更改：
  - 触发管理员消息通知与用户消息通知的方法分别置于不同引用模板
  - 上传图片接口成功时响应的数据增加sha字段（图片唯一标识）

优化：
  - 上传图片的容量可由配置参数MaxUpload控制，默认20Mb

v1.9.1
------

Released in 2020-08-25

- 更改upimg_stream_processor钩子

  1.9.0新增时最终只能有一个钩子成功处理，更改为所有钩子累加处理。

  示例：两个钩子分别进行了裁剪处理、水印处理，最终图片有水印且裁剪过尺寸。

- 更改上传容量限制，10MB增加到20MB，控制台可以设置到20，默认仍然是10

- 增加了安全相关响应标头和cookie字段

- 修复与优化控制台版本升级提示（由服务端判定，以符合语义化2.0标准）

v1.9.0
------

Released in 2020-08-23

功能：
  - 支持钩子扩展静态文件
  - 添加upimg_stream_processor、upimg_stream_interceptor扩展点钩子用于上传时处理图片
  - 登录页面增加login_area模板扩展点
  - 命令行子命令clean增加清理用户无效图片的选项
  - 重构用户脚本（之前是移植 `Search By Image <https://github.com/ccloli/Search-By-Image/>`_ ），代码简洁清晰美观。
  - 设置项增加代理（程序部分对外请求自动调用代理）、新注册用户默认标签
  - 上传图片增加title描述字段，首页上传支持
  - 支持上传临时图片（首页上传不支持，misc/cli.py支持），过期（秒）后清除数据
  - 控制台安装第三方增加类似于应用商店功能，从 `picbed-awesome <https://github.com/sapicd/awesome>`_ 获取开源审核的钩子扩展
  - 添加 :func:`utils.web.set_page_msg` 向管理员控制台发出消息（类似flash）
  - 独立的misc/cli.py命令行上传脚本支持title、expire参数
  - 支持新模式：触发与捕获 :class:`utils.exceptions.ApiError` :class:`utils.exceptions.PageError` 异常
  - 钩子管理器call方法增加any_false模式，任意钩子处理失败时则中止后续

修复：
  - 解决钩子管理器第三方扩展更新后未重新加载
  - 修复我的图片页面存在已删除图片的异常
  - 修复文档大括号

更改：
  - 移除LocalStorage，非核心数据也统一存到redis
  - RedisStorage类使用单例模式

优化：
  - 管理员控制台设置项界面及钩子配置随之调整
  - 请求GitHub的接口内置到服务端并缓存（最新版本接口）
  - 优化up2local的图片保存目录
  - 用于钩子扩展的 ``front.ep`` 路由方法可回调时会执行
  - 钩子扩展 ``__appversion__`` 允许多个规则
  - 启动脚本与gunicorn配置脚本

v1.8.0
------

Released in 2020-07-28

功能：
  - 全站公告
  - 忘记/重置密码
  - 钩子支持appversion元数据
  - 钩子的模板扩展点增加adminscript、userscript、nav
  - 钩子路由方法
  - 用户设置标签（分组）及按标签设置分组上传所用后端
  - 用户审核拒绝提示，拒绝后重新提交申请

修复：
  - 解决textarea类型多行文本造成的页面错误
  - 设置默认SecretKey解决正式环境多workers状态紊乱
  - 解决首页上传设置相册时粘贴文字出现的提示

更改：
  - 删除用户时一并删除用户产生的数据
  - 删除图片时删除数据
  - 正式环境脚本采用-c方式读取picbed.py
  - 打印config便于调试
  - 钩子加载时检测版本是否符号语义化2.0规范
  - 安装第三方包时使用upgrade方式
  - 钩子扩展操作按钮改为图标
  - 内置钩子up2oss、up2cos移除，可无缝改为第三方
  - 钩子管理器call方法args、kwargs已经废弃

优化：
  - 用户管理显示细节增强
  - 用户邮箱验证
  - 设置首页上传区域提示内容时进行HTML过滤
  - 自动处理站点设置中复选框和开关的值
  - Dockerfile和docker-compose.yml，优化缩减尺寸
  - 文档与方法注释

v1.7.0
------

Released in 2020-07-14

功能：
  - 集成文档
  - LinkToken统计中增加解析UserAgent相关字段
  - 升级助手：通过命令行完成升级所需要的数据迁移、字段变更等
  - 增加用户状态字段，实现注册用户审核与审核开关
  - 允许审核用户留言
  - 控制台设置、取消某用户为管理员
  - 用户资料增加邮箱，并支持验证（邮件发送钩子、模板）
  - 钩子管理器调用钩子方法增加_mode、_every

修复：
  - 上一页地址从注册到登录页面的问题

更改：
  - 全局设置中站点后缀改为站点名称
  - 钩子管理器调用钩子方法的args、kwargs参数改为_args、_kwargs

优化：
  - 引用轻量图标字体库，全站增设图标
  - 用户脚本设置LinkToken改为渲染下拉表以供选择
  - 用户脚本上传字段自动跟随全局配置
  - 登录与上传接口，增加最近一次登录时间
  - 钩子管理器调用钩子方法返回执行结果

v1.6.0
------

Released in 2020-06-23

功能：
  - 统计图表
  - 一个从命令行(Win/Mac/Linux)上传的脚本
  - 兼容rediscluster
  - 管理员用户管理及钩子在线安装第三方模块

修复：
  - 油猴脚本exclude排除列表
  - 登录态重定向方法适应
  - 解决我的图片上一页/下一页翻页快捷键偶尔失效

更改：
  - 控制台显示区域布局
  - Dockerfile分阶段构建减少体积，支持docker-compose
  - 更改LinkToken调用统计的设计错误（不兼容旧统计数据）

Previous Versions
-----------------

Go to `GitHub Releases <https://github.com/sapicd/sapic/releases>`_
