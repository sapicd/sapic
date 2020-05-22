#!/bin/bash
#TRAVIS_TAG按版本构建镜像
IMGNAME="registry.cn-beijing.aliyuncs.com/staugur/picbed:${TRAVIS_BRANCH}"
docker build -t $IMGNAME .
echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin registry.cn-beijing.aliyuncs.com
docker push $IMGNAME