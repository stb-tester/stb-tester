#!/bin/sh

#/ Usage: pylint.sh file.py [file.py...]
#/
#/ Runs pep8 and pylint checkers over the given python source files.

[ $# -gt 0 ] || { grep '^#/' "$0" | cut -c4- >&2; exit 1; }

pep8options() {
    # E501: line too long > 80 chars (because pylint does it)
    echo --ignore=E501
}

ret=0
for f in "$@"; do
    r=0
    pylint --rcfile="$(dirname "$0")/pylint.conf" $f || r=1 ret=1
    pep8 $(pep8options $f) $f || r=1 ret=1
    [ $r -eq 0 ] && echo "$f OK"
done
exit $ret
