#!/bin/bash -u

#/ Usage: pylint.sh file.py [file.py...]
#/
#/ Enforces the stb-tester project's coding conventions
#/ by running pep8 and pylint checkers over the given python source files.
#/ Used by 'make check'.

[ $# -gt 0 ] || { grep '^#/' "$0" | cut -c4- >&2; exit 1; }

ret=0

if pycodestyle --version &>/dev/null; then
    # E124: closing bracket does not match visual indentation
    # E203: whitespace before ':'
    # E227: missing whitespace around bitwise or shift operator
    # E241: multiple spaces after ',' (because pylint does it)
    # E301: expected 1 blank line (because pylint does it)
    # E305: expected 2 blank lines after class or function definition (pylint)
    # E402: module level import not at top of file (because pylint does it)
    # E501: line too long > 80 chars (because pylint does it)
    # E711: comparison to None should be 'if cond is not None:' (because I need to do that in unit tests)
    # E721: do not compare types, use 'isinstance()' (because pylint does it)
    # E722: do not use bare except (because pylint does it)
    # E731: do not assign a lambda expression, use a def
    # E741: do not use variables named ‘l’, ‘O’, or ‘I’
    # W291: trailing whitespace (because pylint does it)
    # W504: line break after binary operator
    pycodestyle --ignore=E124,E203,E227,E241,E301,E305,E402,E501,E711,E721,E722,E731,E741,W291,W504 "$@" || ret=1
else
    echo "warning: pycodestyle not installed; skipping pycodestyle and only running pylint" >&2
fi

$PYLINT --version

out=$($PYLINT "$@" 2>&1) || ret=1
printf "%s" "$out" |
    grep -v \
        -e 'libdc1394 error: Failed to initialize libdc1394' \
        -e 'pygobject_register_sinkfunc is deprecated' \
        -e "assertion .G_TYPE_IS_BOXED (boxed_type). failed" \
        -e "assertion .G_IS_PARAM_SPEC (pspec). failed" \
        -e "return isinstance(object, (type, types.ClassType))" \
        -e "return isinstance(object, type)" \
        -e "gsignal.c:.*: parameter 1 of type '<invalid>' for signal \".*\" is not a value type" \
        -e "astroid.* Use gi.require_version" \
        -e "^  __import__(m)$"

exit $ret
