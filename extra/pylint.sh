#!/bin/bash

#/ Usage: pylint.sh file.py [file.py...]
#/
#/ Enforces the stb-tester project's coding conventions
#/ by running pep8 and pylint checkers over the given python source files.
#/ Used by 'make check'.

[ $# -gt 0 ] || { grep '^#/' "$0" | cut -c4- >&2; exit 1; }

pep8options() {
    # E501: line too long > 80 chars (because pylint does it)
    echo --ignore=E501
}

ret=0
for f in "$@"; do
    r=0
    out=$(pylint --rcfile="$(dirname "$0")/pylint.conf" \
                 $f 2>&1) || r=1 ret=1
    printf "%s" "$out" |
        grep -v \
            -e 'pygobject_register_sinkfunc is deprecated' \
            -e "assertion .G_TYPE_IS_BOXED (boxed_type). failed" \
            -e "assertion .G_IS_PARAM_SPEC (pspec). failed" \
            -e "return isinstance(object, (type, types.ClassType))"
    pep8 $(pep8options $f) $f || r=1 ret=1
    if which isort &>/dev/null; then
        isort --check-only $f >/dev/null || r=1 ret=1;
    fi
    [ $r -eq 0 ] && echo "$f OK"
done
exit $ret
