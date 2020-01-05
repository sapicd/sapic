# picbed

基于Flask的Web自建图床，默认存储在本地，支持扩展又拍云、七牛云、阿里云OSS、腾讯云COS等后端存储。

[![Build Status](https://travis-ci.org/staugur/picbed.svg?branch=master)](https://travis-ci.org/staugur/picbed)
[![codecov](https://codecov.io/gh/staugur/picbed/branch/master/graph/badge.svg)](https://codecov.io/gh/staugur/picbed)

## 部署

大致部署说明（后续Release时发布详细文档）

1. 要求： Python2.7、Python3.5+和Redis

2. 下载： `git clone https://github.com/staugur/picbed && cd picbed/src`

3. 依赖： `pip install -r requirements.txt`

4. 配置： `config.py`即配置文件，可以从环境变量中读取配置信息，必需的是picbed_redis_url

5. 启动： 
```
    $ python cli.py -sa            # 首先创建一个管理员账号
    $ make run                     # 开发环境启动
    $ sh online_gunicorn.sh start  # 正式环境，若需前台启动，将start换成run即可
```

## 扩展钩子

通过所谓的钩子扩展功能点，目前在图片保存时有一个钩子，可以藉此扩展后端存储。

目前我写的钩子如下：

| 名称 | 作用 | GitHub |
| --- | --- | --- |
| up2upyun | 将图片保存到又拍云USS中 | [staugur/picbed-up2upyun](https://github.com/staugur/picbed-up2upyun) |

## 预览图

目前beta版本基本完成，先来几张预览图（PS：前几张大概是平板效果，最后一张是PC效果）

![未登录首页](./Snapshot/1.png)

![登录页面](./Snapshot/2.png)

![首页上传效果](./Snapshot/3.png)

![首页上传复制](./Snapshot/4.png)

![控制台管理员功能](./Snapshot/5.png)

![管理我的图片](./Snapshot/6.png)
