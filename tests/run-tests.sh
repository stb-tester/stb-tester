#!/bin/bash

# Automated tests to test the stb-tester framework itself.
# See SETUP TIPS in ../README.rst for further information.

#/ Usage: run-tests.sh [options] [testnames...]
#/
#/         -l      Leave the scratch dir created in /tmp.
#/         -v      Verbose (don't suppress console output from tests).
#/
#/         If any test names are specified, only those test cases will be run.

cd "$(dirname "$0")"
testdir="$PWD"
for tests in ./test-*.sh; do
    source $tests
done

while getopts "lv" option; do
    case $option in
        l) leave_scratch_dir=true;;
        v) verbose=true;;
        *) grep '^#/' < "$0" | cut -c4- >&2; exit 1;; # Print usage message
    esac
done
shift $(($OPTIND-1))

export PATH="$testdir/..:$PATH"
export STBT_CONFIG_FILE="$testdir/stbt.conf"
export GST_PLUGIN_PATH="$testdir/../gst:$GST_PLUGIN_PATH"
rm -f ~/.gstreamer-0.10/registry.*

run() {
    scratchdir=$(mktemp -d -t stb-tester.XXX)
    printf "$1... "
    $1 > "$scratchdir/log" 2>&1
    local status=$?
    [ $status -eq 0 ] && echo "OK" || echo "FAIL"
    if [[ "$verbose" = "true" || $status -ne 0 ]]; then
        echo "Showing '$scratchdir/log':"
        cat "$scratchdir/log"
    fi
    if [[ "$leave_scratch_dir" != "true" && $status -eq 0 ]]; then
        rm -rf "$scratchdir/log" "$scratchdir/gst-launch.log" \
            "$scratchdir/test.py" "$scratchdir/in-script-dir.png" \
            "$scratchdir/stbt.conf" \
            "$scratchdir/readme" "$scratchdir/expected" \
            "$scratchdir/stbt_helpers" "$scratchdir/stbt_tests" \
            "$scratchdir/get-screenshot.py" "$scratchdir/match-screenshot.py" \
            "$scratchdir/gamut.png"
        rmdir "$scratchdir"
    fi
    [ $status -eq 0 ]
}

# Portable timeout command. Usage: timeout <secs> <command> [<args>...]
timeout() { perl -e \
    'alarm shift @ARGV;
     exec @ARGV;
     print "timeout: command not found: @ARGV\n";
     exit 1;' \
    "$@"; }
timedout=142

############################################################################

if [ $# -eq 0 ]; then

    echo "Testing gstreamer + OpenCV installation:" &&
    run test_gstreamer_core_elements &&
    run test_gstreamer_can_find_templatematch &&
    run test_gsttemplatematch_has_all_element_properties &&
    run test_gsttemplatematch_defaults_match_stbt_conf &&
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
    run test_stbt_motiondetect_with_high_noisethreshold_reports_motion &&
    run test_stbt_motiondetect_with_low_noisethreshold_does_not_report_motion &&
    run test_stbt_motiondetect_reports_motion_on_progress_dots &&

    echo "Testing stbt-run:" &&
    run test_wait_for_match &&
    run test_wait_for_match_no_match &&
    run test_wait_for_match_changing_template &&
    run test_wait_for_match_nonexistent_template &&
    run test_wait_for_match_noise_threshold_raises_warning &&
    run test_wait_for_match_match_method_param_affects_first_pass &&
    run test_wait_for_match_match_threshold_param_affects_match &&
    run test_wait_for_match_confirm_method_none_matches_anything_with_match_threshold_zero &&
    run test_wait_for_match_confirm_methods_produce_different_results &&
    run test_wait_for_match_erode_passes_affects_match &&
    run test_wait_for_match_confirm_threshold_affects_match &&
    run test_detect_match_nonexistent_template &&
    run test_press_until_match &&
    run test_wait_for_match_searches_in_script_directory &&
    run test_press_until_match_searches_in_script_directory &&
    run test_detect_match_searches_in_script_directory &&
    run test_detect_match_searches_in_library_directory &&
    run test_detect_match_searches_in_caller_directory &&
    run test_wait_for_motion_int &&
    run test_wait_for_motion_str &&
    run test_wait_for_motion_no_motion_int &&
    run test_wait_for_motion_no_motion_str &&
    run test_wait_for_motion_half_motion_str_2of4 &&
    run test_wait_for_motion_half_motion_str_2of3 &&
    run test_wait_for_motion_half_motion_str_3of4 &&
    run test_wait_for_motion_half_motion_int &&
    run test_wait_for_motion_nonexistent_mask &&
    run test_changing_input_video_with_the_test_control &&
    run test_detect_match_reports_match &&
    run test_detect_match_reports_match_position &&
    run test_detect_match_reports_valid_timestamp &&
    run test_detect_match_reports_no_match &&
    run test_detect_match_times_out &&
    run test_detect_motion_with_debug_output_does_not_segfault_without_mask &&
    run test_detect_match_times_out_during_yield &&
    run test_detect_match_changing_template_is_not_racy &&
    run test_detect_match_example_press_and_wait_for_match &&
    run test_detect_motion_reports_motion &&
    run test_detect_motion_reports_valid_timestamp &&
    run test_detect_motion_reports_no_motion  &&
    run test_detect_motion_times_out &&
    run test_detect_motion_times_out_during_yield &&
    run test_detect_motion_changing_mask &&
    run test_detect_motion_changing_mask_is_not_racy &&
    run test_detect_motion_example_press_and_wait_for_no_motion &&
    run test_precondition_script &&
    run test_get_frame_and_save_frame &&
    run test_get_config &&

    echo "Testing stbt-record:" &&
    run test_record &&

    echo "Testing stbt-config:" &&
    run test_that_stbt_config_reads_from_STBT_CONFIG_FILE &&
    run test_that_stbt_config_searches_in_specified_section &&
    run test_that_stbt_config_returns_failure_on_key_not_found &&

    echo "Testing stbt-screenshot:" &&
    run test_that_stbt_screenshot_saves_file_to_disk &&

    echo "Testing stbt-templatematch:" &&
    run test_that_stbt_templatematch_finds_match &&
    run test_that_stbt_templatematch_doesnt_find_match &&
    run test_that_stbt_templatematch_applies_confirm_threshold_parameter &&

    echo "Testing 'make doc':" &&
    run test_that_readme_default_templatematch_values_are_kept_up_to_date &&
    run test_that_readme_python_api_docs_are_kept_up_to_date &&

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
