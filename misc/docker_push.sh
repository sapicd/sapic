#!/bin/bash
tag=$TRAVIS_BRANCH
if [ "$tag" = "master" ]; then
    tag=latest
fi
IMGNAME="registry.cn-beijing.aliyuncs.com/staugur/picbed:${tag}"
docker build -t $IMGNAME .
echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin registry.cn-beijing.aliyuncs.com
docker push $IMGNAME