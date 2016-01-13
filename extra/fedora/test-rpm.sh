#!/bin/bash

[[ $# -gt 0 ]] || { echo "error: No rpm files specified" >&2; exit 1; }

this_dir=$(dirname $0)
stbt_dir=$(cd $this_dir/../.. && pwd)
set -x

docker rm -f test-stb-tester-fedora-rpm &>/dev/null
docker run -t \
    --name test-stb-tester-fedora-rpm \
    $(for rpm in "$@"; do
        echo "-v $PWD/$rpm:/tmp/$rpm:ro"
      done | tr '\n' ' ') \
    -v $stbt_dir:/usr/src/stb-tester:ro \
    fedora:23 \
    /bin/bash -c "
        set -x &&
        dnf install -y man ${*/#/tmp/} &&
        stbt --version &&
        stbt --help &&
        man stbt | cat &&
        cd /usr/src/stb-tester &&
        ./tests/run-tests.sh -i"
