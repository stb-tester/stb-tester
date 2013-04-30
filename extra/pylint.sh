#!/bin/sh

#/ Usage: pylint.sh file.py [file.py...]
#/
#/ Runs pep8 and pylint checkers over the given python source files.

[ $# -gt 0 ] || { grep '^#/' "$0" | cut -c4- >&2; exit 1; }

pylintoptions() {
    # C0103: Invalid name for type <T>
    # W0142: Used * or ** magic
    # I001[12]: Locally disabling/enabling W0123
    echo --disable=C0103,W0142,I0011,I0012

    # C0111: Missing docstring
    # C0302: Too many lines in module
    # W0603: Using the global statement
    case "$1" in
        irnetbox.py) echo --disable=C0111;;
        stbt.py) echo --disable=C0302,W0603;;
        stbt-record) echo --disable=C0111;;
    esac
}
pep8options() {
    # E501: line too long > 80 chars (because pylint does it)
    case "$1" in
        irnetbox.py) echo --ignore=E501;;
        stbt.py) echo --ignore=E501;;
    esac
}

ret=0
for f in "$@"; do
    r=0
    pylint --rcfile="$(dirname "$0")/pylint.conf" \
        $(pylintoptions $f) $f || r=1 ret=1
    pep8 $(pep8options $f) $f || r=1 ret=1
    [ $r -eq 0 ] && echo "$f OK"
done
exit $ret
