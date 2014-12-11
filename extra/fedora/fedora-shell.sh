#!/bin/bash

# Gives you a bash shell in a Fedora container, with your stb-tester working
# copy available at (and $PWD set to) /home/stb-tester.

this_dir=$(dirname $0) &&
stbt_dir=$(cd $this_dir/../.. && pwd) &&

$this_dir/build-docker-image.sh &&

exec docker run -ti --rm \
    -v $stbt_dir:/home/stb-tester \
    -v $HOME/.config/copr:/home/stb-tester/.config/copr:ro \
    -v $HOME/.gitconfig:/home/stb-tester/.gitconfig:ro \
    stbtester/stb-tester-fedora-build-environment \
    /bin/bash "$@"
