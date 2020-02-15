# picbed

基于Flask的Web自建图床，默认存储在本地，支持扩展又拍云、七牛云、阿里云OSS、腾讯云COS等后端存储。

[![Build Status](https://travis-ci.org/staugur/picbed.svg?branch=master)](https://travis-ci.org/staugur/picbed)
[![codecov](https://codecov.io/gh/staugur/picbed/branch/master/graph/badge.svg)](https://codecov.io/gh/staugur/picbed)

## 部署

1. 要求： Python2.7、Python3.5+（含PyPy）和Redis

2. 下载： `git clone https://github.com/staugur/picbed && cd picbed/src`

3. 依赖： `pip install -r requirements.txt`

4. 配置：
```
config.py即配置文件，首先从环境变量中读取配置信息，无法找到时使用内置默认值，
必需的是picbed_redis_url。

所需环境变量可以配置到如 全局或家目录.bash_profile 文件中，不过推荐的是写入到 程序目录下.env 文件里，
它不会被提交到仓库，而程序启动时配置文件会先加载其中的环境变量，格式是k=v，
比如：

picbed_redis_url=redis://@localhost
```

5. 启动： 
```
// 首先创建一个管理员账号 -h/--help显示帮助
$ flask sa create -u USER -p PASSWORD --isAdmin

// 开发环境启动
$ make run
// 正式环境，若需前台启动，将start换成run即可
$ sh online_gunicorn.sh start
```

6. Nginx:
```
// 默认配置下，picbed启动监听127.0.0.1:9514，nginx配置示例：
server {
    listen 80;
    server_name picbed.domain.name;
    charset utf-8;
    client_max_body_size 12M;
    location ~ ^\/static\/.*$ {
        root /path/to/picbed/src/;
    }
    location / {
       proxy_pass http://127.0.0.1:9514;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-Proto $scheme;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## 文档

详细文档请访问：[Picbed Docs](https://docs.saintic.com/picbed)

## TODO

转移到[GitHub Projects](https://github.com/staugur/picbed/projects/2)

## 演示站

https://picbed.saintic.com

测试账号：test

测试密码：123456

对外服务(请勿修改密码)，允许匿名上传，但是目前上传的图片保留删除权利！

## 扩展钩子

通过所谓的钩子扩展功能点，目前在图片保存时有一个钩子，可以藉此扩展后端存储。

目前我写的钩子如下：

| 名称 | 作用 | GitHub |
| ---- | ----- | ----- |
| up2upyun | 将图片保存到又拍云USS中 | [staugur/picbed-up2upyun](https://github.com/staugur/picbed-up2upyun) |
| up2qiniu | 将图片保存到七牛云KODO中 | [staugur/picbed-up2qiniu](https://github.com/staugur/picbed-up2qiniu) |
| up2oss | 将图片保存到阿里云OSS中 | [staugur/picbed-up2oss](https://github.com/staugur/picbed-up2oss) |
| up2cos | 将图片保存到腾讯云COS中 | [staugur/picbed-up2cos](https://github.com/staugur/picbed-up2cos) |
| up2smms | 将图片保存到sm.ms中 | [staugur/picbed-up2smms](https://github.com/staugur/picbed-up2smms) |
| up2superbed | 将图片保存到聚合图床`superbed.cn` | [staugur/picbed-up2superbed](https://github.com/staugur/picbed-up2superbed) |
| passport | 接入passport登录 | [staugur/picbed-ssoclient](https://github.com/staugur/picbed-ssoclient) |

## 客户端上传

#### - 使用PicGo上传到自定义的picbed图床

[下载PicGo](https://github.com/Molunerfinn/PicGo/releases)并安装，打开主界面，在 **插件设置** 中搜索 **web-uploader** 并安装，然后在 **图床设置-自定义Web图床** 中按照如下方式填写：

```
url: http[s]://你的picbed域名/api/upload
paramName: picbed
jsonPath: src
# 以上是匿名上传，仅在管理员开启匿名时才能上传成功
# 如需登录上传，请使用token(在控制台-个人资料-Token查看)，以下两种任选:
customHeader: {"Authorization": "Token 你的Token值"}
customBody: {"token": "你的Token值"}
```

设置完之后选择自定义Web图床为默认图床即可。

## 预览图

目前beta版本基本完成，先来几张预览图（PS：前几张大概是平板效果，最后一张是PC效果）

![未登录首页](./Snapshot/1.png)

![登录页面](./Snapshot/2.png)

![首页上传效果](./Snapshot/3.png)

![首页上传复制](./Snapshot/4.png)

![控制台管理员功能](./Snapshot/5.png)

![管理我的图片](./Snapshot/6.png)
