#!/bin/bash

# Automated tests to test the stb-tester framework itself.

#/ Usage: run-tests.sh [options] [testsuite or testcase names...]
#/
#/         -i      Run against installed version of stbt
#/         -l      Leave the scratch dir created in /tmp.
#/         -v      Verbose (don't suppress console output from tests).
#/
#/         If any test names are specified, only those test cases will be run.


while getopts "lvi" option; do
    case $option in
        i) test_installation=true;;
        l) leave_scratch_dir=true;;
        v) verbose=true;;
        *) grep '^#/' < "$0" | cut -c4- >&2; exit 1;; # Print usage message
    esac
done
shift $(($OPTIND-1))

export testdir="$(cd "$(dirname "$0")" && pwd)"
export srcdir="$testdir/.."
export GST_PLUGIN_PATH="$srcdir/gst:$GST_PLUGIN_PATH"
export PYTHONPATH="$srcdir:$PYTHONPATH"
export PYTHONUNBUFFERED=x
export PYLINTRC="$testdir/pylint.conf"

testsuites=()
testcases=()
while [[ $# -gt 0 ]]; do
    [[ -f $1 ]] && testsuites+=($1) || testcases+=($1)
    shift
done
for testsuite in ${testsuites[*]:-"$(dirname "$0")"/test-*.sh}; do
    source $testsuite
done
: ${testcases:=$(declare -F | awk '/ test_/ {print $3}')}

cd "$testdir"
rm -f ~/.gstreamer-1.0/registry.*

if [[ "$test_installation" != "true" ]]; then
    test_installation_prefix="$(mktemp -d -t stbt-test-installation.XXXXXX)"
    make -C "$srcdir" install "prefix=$test_installation_prefix"
    export PATH="$test_installation_prefix/bin:$PATH"
fi

. $testdir/utils.sh

run() {
    scratchdir=$(mktemp -d -t stb-tester.XXX)
    [ -n "$scratchdir" ] || { echo "$0: mktemp failed" >&2; exit 1; }
    mkdir -p "$scratchdir/config/stbt"
    export XDG_CONFIG_HOME="$scratchdir/config"
    unset STBT_CONFIG_FILE
    cp "$testdir/stbt.conf" "$scratchdir/config/stbt"
    printf "$1... "
    ( cd "$scratchdir" && $1 ) > "$scratchdir/log" 2>&1
    local status=$?
    case $status in
        0) echo "OK";;
        77) status=0; echo "SKIPPED";;
        *) echo "FAIL";;
    esac
    if [[ "$verbose" = "true" || $status -ne 0 ]]; then
        echo "Showing '$scratchdir/log':"
        cat "$scratchdir/log"
        echo ""
    fi
    if [[ "$leave_scratch_dir" != "true" && $status -eq 0 ]]; then
        rm -rf "$scratchdir"
    fi
    [ $status -eq 0 ]
}

# Run the tests ############################################################
ret=0
for t in ${testcases[*]}; do
    run $t || ret=1
done
if [[ -n "$test_installation_prefix" ]]; then
    rm -rf "$test_installation_prefix"
fi
exit $ret


# bash-completion script: Add the below to ~/.bash_completion
_stbt_run_tests() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local testdir="$(dirname \
        $(echo $COMP_LINE | grep -o '\b[^ ]*run-tests\.sh\b'))"
    local testfiles="$(\ls $testdir/test-*.sh | sed -e 's,^\./,,')"
    local testcases="$(awk -F'[ ()]' '/^test_[a-z_]*\(\)/ {print $1}' $testfiles)"
    COMPREPLY=( $(
        compgen -W "$testcases $testfiles" -- "$cur") )
}
complete -F _stbt_run_tests run-tests.sh
