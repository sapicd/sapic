.. _picbed-changelog:

=========
更新日志
=========

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
  - 控制台安装第三方增加类似于应用商店功能，从 `picbed-awesome <https://github.com/staugur/picbed-awesome>`_ 获取开源审核的钩子扩展
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

Go to `GitHub Releases <https://github.com/staugur/picbed/releases>`_