#!/bin/bash

rpm=$1
[[ -n "$rpm" ]] || { echo "error: rpm file not specified" >&2; exit 1; }

this_dir=$(dirname $0)
stbt_dir=$(cd $this_dir/../.. && pwd)
set -x

docker rm -f test-stb-tester-fedora-rpm &>/dev/null
docker run -t \
    --name test-stb-tester-fedora-rpm \
    -v $(pwd)/$rpm:/tmp/$rpm:ro \
    -v $stbt_dir:/usr/src/stb-tester:ro \
    fedora:20 \
    /bin/bash -c "
        set -x &&
        sudo yum install -y /tmp/$rpm &&
        stbt --version &&
        stbt --help &&
        man stbt | cat &&
        cd /usr/src/stb-tester &&
        ./tests/run-tests.sh -i tests/test-match.sh"
