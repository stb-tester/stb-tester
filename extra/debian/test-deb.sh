#!/bin/bash

[[ $# -gt 0 ]] || { echo "error: No deb files specified" >&2; exit 1; }

this_dir=$(dirname $0)
stbt_dir=$(cd $this_dir/../.. && pwd)
set -x

docker rm -f test-stb-tester-ubuntu-pkg &>/dev/null
docker run -t \
    --name test-stb-tester-ubuntu-pkg \
    $(for pkg in "$@"; do
        echo "-v $PWD/$pkg:/tmp/$pkg:ro"
      done | tr '\n' ' ') \
    -v $stbt_dir:/usr/src/stb-tester:ro \
    ubuntu:18.04 \
    /bin/bash -c "
        set -x &&
        export DEBIAN_FRONTEND=noninteractive &&
        apt-get update &&
        { dpkg -i ${*/#//tmp/}; true; } &&
        apt-get --fix-broken -y install &&
        apt-get -y install man time &&
        stbt --version &&
        stbt --help &&
        man stbt | cat &&
        cd /usr/src/stb-tester &&
        ./tests/run-tests.sh -i"
