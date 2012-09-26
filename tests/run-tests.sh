#!/bin/bash

# Automated tests to test the stb-tester framework itself.
# See SETUP TIPS in ../README.rst for further information.

cd "$(dirname "$0")"
testdir="$PWD"
for tests in ./test-*.sh; do
    source $tests
done

export STBT_CONFIG_FILE="$testdir/stbt.conf"
export GST_PLUGIN_PATH="$testdir/../gst:$GST_PLUGIN_PATH"

run() {
    GST_DEBUG=
    scratchdir=$(mktemp -d -t stb-tester.XXX)
    printf "$1... "
    $1 > "$scratchdir/log" 2>&1
    if [ $? -eq 0 ]; then
        echo "OK"
        rm -f "$scratchdir/log" "$scratchdir/gst-launch.log" \
            "$scratchdir/test.py" "$scratchdir/in-script-dir.png" \
            "$scratchdir/stbt.conf"
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

    echo "Testing gstreamer stbt-motiondetect element:" &&
    run test_gstreamer_can_find_stbt_motiondetect &&
    run test_stbt_motiondetect_is_not_active_by_default &&
    run test_stbt_motiondetect_is_not_active_when_disabled &&
    run test_stbt_motiondetect_reports_motion &&
    run test_stbt_motiondetect_does_not_report_motion &&
    run test_stbt_motiondetect_with_mask_reports_motion &&
    run test_stbt_motiondetect_with_mask_does_not_report_motion &&

    echo "Testing stbt-run:" &&
    run test_wait_for_match &&
    run test_wait_for_match_no_match &&
    run test_wait_for_match_changing_template &&
    run test_wait_for_match_nonexistent_template &&
    run test_press_until_match &&
    run test_wait_for_match_searches_in_script_directory &&
    run test_press_until_match_searches_in_script_directory &&
    run test_wait_for_motion &&
    run test_wait_for_motion_no_motion &&
    run test_wait_for_motion_nonexistent_mask &&
    run test_changing_input_video_with_the_test_control &&
    run test_detect_match_reports_match &&
    run test_detect_match_reports_match_position &&
    run test_detect_match_reports_valid_timestamp &&
    run test_detect_match_reports_no_match &&
    run test_detect_match_times_out &&
    run test_detect_match_times_out_during_yield &&
    run test_detect_match_example_press_and_wait_for_match &&
    run test_detect_motion_reports_motion &&
    run test_detect_motion_reports_valid_timestamp &&
    run test_detect_motion_reports_no_motion  &&
    run test_detect_motion_times_out &&
    run test_detect_motion_times_out_during_yield &&
    run test_detect_motion_changing_mask &&
    run test_detect_motion_example_press_and_wait_for_no_motion &&
    run test_precondition_script &&

    echo "Testing stbt-record:" &&
    run test_record &&

    echo "All passed." || exit

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
