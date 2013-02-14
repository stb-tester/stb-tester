#!/bin/sh

#/ Usage: pylint.sh file.py [file.py...]
#/
#/ Runs pep8 and pylint checkers over the given python source files.

[ $# -gt 0 ] || { grep '^#/' "$0" | cut -c4- >&2; exit 1; }

pylintoptions() {
    case "$1" in
        stbt.py) echo --disable=E1101;;
    esac
}
pep8options() {
    case "$1" in
        irnetbox.py) echo --ignore=E203,E225,E251,E501;;
    esac
}

ret=0
for f in "$@"; do
    r=0
    pylint --rcfile="$(dirname "$0")/pylint.conf" --errors-only \
        $(pylintoptions $f) $f || r=1 ret=1
    pep8 $(pep8options $f) $f || r=1 ret=1
    [ $r -eq 0 ] && echo "$f OK"
done
exit $ret
