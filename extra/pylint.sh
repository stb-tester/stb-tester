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
    out=$(pylint --rcfile="$(dirname "$0")/pylint.conf" $f 2>&1) || r=1 ret=1
    printf "%s" "$out" | grep -v 'pygobject_register_sinkfunc is deprecated'
    pep8 $(pep8options $f) $f || r=1 ret=1
    [ $r -eq 0 ] && echo "$f OK"
done
exit $ret
