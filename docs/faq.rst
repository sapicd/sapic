.. _picbed-faq:

====
FAQ
====

1. 未配置redis
----------------

状况：

开发方式启动没异常，或者出现 ``ValueError: Invalid redis url``

访问页面时出现（正式环境启动时会出现此错误）：

    ``AttributeError: 'NoneType' object has no attribute 'hget'``

解决：配置redis即可，设置环境变量picbed_redis_url或写入.cfg配置文件

2. 配置了redis但未启动redis服务
-----------------------------------------

状况： ``ConnectionError: Error 111 connecting to localhost:6379. Connection refused.``

解决：启动即可

3. redis服务有密码，但配置中没有
-----------------------------------------

状况： ``AuthenticationError: Authentication required.``

解决：

redis配置格式是 ``redis://[:password]@host:port/db``

如果没有密码，去掉 ``[:password]`` ，有密码就需要加上，注意：有冒号，没有中括号。

4. redis服务没有密码，但配置中有
-----------------------------------------

状况： ``AuthenticationError: Client sent AUTH, but no password is set``

解决：去掉配置中密码部分，或者redis加上密码重启redis服务

5. 正式环境多worker下登录状态紊乱
------------------------------------------

状况：在正式环境启动了多个工作进程（gunicorn workers），由于web应用的密钥
随机生成的原因，多进程之间没有共享，所以会出现登录后，刷新页面又不是登录
状态了。

解决：1.8修复此问题，固定了密钥，之前的版本可以在环境变量或配置文件.cfg中
设置 ``picbed_secretkey`` 为一个固定复杂的值。

ps：docker-compose用户可以在docker-compose.yml中添加以下变量再构建启动（大概是第10行picbed_redis_url下面）：

.. code-block::

    - picbed_secretkey = abcdefg
