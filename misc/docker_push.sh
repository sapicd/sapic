#!/bin/bash
tag="$TRAVIS_BRANCH"
if [ -z "$tag" ] || [ "$tag" = "master" ]; then
    tag="latest"
fi
IMGNAME="staugur/picbed:${tag}"
docker build -t $IMGNAME . --build-arg ALPINEMIRROR=dl-cdn.alpinelinux.org --build-arg DEBIANMIRROR=deb.debian.org --build-arg PIPMIRROR=https://pypi.org/simple
echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin
docker push $IMGNAME
