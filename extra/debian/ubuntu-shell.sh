#!/bin/bash

# Gives you a bash shell in an Ubuntu 18.04 container, with your stb-tester
# working copy available at (and $PWD set to) /home/stb-tester.

build_docker_image() {
    deps=$(sed -n '/^Build-Depends:/,/^$/ p' control |
           sed -e 's/Build-Depends://' -e 's/(.*)//' |
           tr -s '\n,' ' ')
    cat Dockerfile.in |
    sed "s/@BUILDDEPENDS@/$deps/" |
    docker build -t stbtester/stb-tester-ubuntu-build-environment -
}

set -ex

cd "$(dirname "$0")"

build_docker_image

exec docker run -ti --rm \
    -v "$PWD"/../..:/home/stb-tester \
    -v "$HOME"/.gitconfig:/home/stb-tester/.gitconfig:ro \
    -v "$HOME"/.gnupg:/home/stb-tester/.gnupg \
    stbtester/stb-tester-ubuntu-build-environment \
    /bin/bash "$@"
