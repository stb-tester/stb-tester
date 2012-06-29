#!/bin/sh

# Automated tests to test the stb-tester framework itself.
# See SETUP TIPS in ../README.rst for further information.

cd "$(dirname "$0")"
for tests in ./test-*.sh; do
    source $tests
done

run() {
    GST_DEBUG=
    scratchdir=$(mktemp -d -t stb-tester.XXX)
    printf "$1... "
    $1 > "$scratchdir/log" 2>&1
    if [ $? -eq 0 ]; then
        echo "OK"
        rm -f "$scratchdir/log" "$scratchdir/gst-launch.log" \
            "$scratchdir/test.py" "$scratchdir/in-script-dir.png"
        rmdir "$scratchdir"
        true
    else
        echo "FAIL"
        echo "See '$scratchdir/log'"
        false
    fi
}

# Portable timeout command. Usage: timeout <secs> <command> [<args>...]
timeout() { perl -e 'alarm shift @ARGV; exec @ARGV' "$@"; }
timedout=142

############################################################################

if [ $# -eq 0 ]; then

    echo "Testing gstreamer + OpenCV installation:" &&
    run test_gstreamer_core_elements &&
    run test_gstreamer_can_find_templatematch &&
    run test_gsttemplatematch_does_find_a_match &&
    run test_gsttemplatematch_bgr_fix &&

    echo "Testing stbt-run:" &&
    run test_wait_for_match &&
    run test_wait_for_match_no_match &&
    run test_wait_for_match_changing_template &&
    run test_wait_for_match_nonexistent_template &&
    run test_wait_for_match_searches_in_script_directory &&
    run test_changing_input_video_with_the_test_control &&

    echo "All passed."

else
    for t in $*; do
        run $t || exit
    done
fi

exit 0


# bash-completion script: Add the below to ~/.bash_completion
_stbt_run_tests() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local testdir="$(dirname \
        $(echo $COMP_LINE | grep -o '\b[^ ]*run-tests\.sh\b'))"
    local testfiles="$(\ls $testdir/test-*.sh)"
    local testcases="$(awk -F'[ ()]' '/^test_[a-z_]*()/ {print $1}' $testfiles)"
    COMPREPLY=( $(compgen -W "$testcases" -- "$cur") )
}
complete -F _stbt_run_tests run-tests.sh
