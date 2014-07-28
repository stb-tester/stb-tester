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

# Disable pylint options that aren't present in all versions of pylint (if you
# use "--disable=C0330" with pylint < 1.2 it raises an "Unknown message"
# exception). Our Travis CI server runs Ubuntu 12.04 with pylint 0.25.
pylintdisables=
for x in C0330; do
    pylint --list-msgs 2>/dev/null | grep -q $x && pylintdisables+=$x,
done
[[ -n "$pylintdisables" ]] && pylintdisables="--disable=$pylintdisables"

ret=0
for f in "$@"; do
    r=0

    out=$(pylint --rcfile="$(dirname "$0")/pylint.conf" $pylintdisables \
                 $f 2>&1) || r=1 ret=1
    printf "%s" "$out" |
        grep -v \
            -e 'pygobject_register_sinkfunc is deprecated' \
            -e "assertion .G_TYPE_IS_BOXED (boxed_type). failed" \
            -e "assertion .G_IS_PARAM_SPEC (pspec). failed" \
            -e "return isinstance(object, (type, types.ClassType))" \
            -e "gsignal.c:.*: parameter 1 of type '<invalid>' for signal \".*\" is not a value type"

    pep8 $(pep8options $f) $f || r=1 ret=1

    # PEP8-compliant order of 'import' statements
    if which isort &>/dev/null; then
        if ! isort --check-only $f >/dev/null; then
            isort --version
            isort --diff $f
            r=1 ret=1
        fi
    fi

    [ $r -eq 0 ] && echo "$f OK"
done
exit $ret
