#!/bin/bash

#/ Usage: pylint.sh file.py [file.py...]
#/
#/ Enforces the stb-tester project's coding conventions
#/ by running pep8 and pylint checkers over the given python source files.
#/ Used by 'make check'.

[ $# -gt 0 ] || { grep '^#/' "$0" | cut -c4- >&2; exit 1; }

pep8options() {
    # E124: closing bracket does not match visual indentation
    # E402: module level import not at top of file (because isort does it)
    # E501: line too long > 80 chars (because pylint does it)
    # E721: do not compare types, use 'isinstance()' (because pylint does it)
    # E731: do not assign a lambda expression, use a def
    echo --ignore=E124,E402,E501,E721,E731
}

ret=0
for f in "$@"; do
    r=0

    out=$(pylint --rcfile="$(dirname "$0")/pylint.conf" $f 2>&1) || r=1 ret=1
    printf "%s" "$out" |
        grep -v \
            -e 'libdc1394 error: Failed to initialize libdc1394' \
            -e 'pygobject_register_sinkfunc is deprecated' \
            -e "assertion .G_TYPE_IS_BOXED (boxed_type). failed" \
            -e "assertion .G_IS_PARAM_SPEC (pspec). failed" \
            -e "return isinstance(object, (type, types.ClassType))" \
            -e "gsignal.c:.*: parameter 1 of type '<invalid>' for signal \".*\" is not a value type" \
            -e "astroid.* Use gi.require_version" \
            -e "^  __import__(m)$"

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
