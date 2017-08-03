# Run with ./run-tests.sh

create_test_repo() {
    which git &>/dev/null || skip "git is not installed"
    (
        git init tests &&
        cd tests &&
        git config user.name "Stb Tester" &&
        git config user.email "test-stbt-batch@stb-tester.com" &&
        cp "$testdir/test.py" "$testdir/test2.py" "$testdir/test_functions.py" \
           "$testdir"/test_{success,error,failure}.py \
           "$testdir/videotestsrc-checkers-8.png" \
           "$testdir/videotestsrc-gamut.png" . &&
        git add . &&
        git commit -m "Initial commit"
    ) >/dev/null 2>&1 || fail "Failed to set up git repo"
}

validate_testrun_dir() {
    local d="$1" testname="$2" commit="$3" commit_sha="$4" extra_column="$5"

    [[ -f "$d/combined.log" ]] || fail "$d/combined.log not created"
    [[ $(cat "$d/exit-status") == 0 ]] || fail "wrong $d/exit-status"
    [[ $(cat "$d/test-name") == "$testname" ]] || fail "wrong $d/test-name"
    diff -u <(cat "$srcdir"/VERSION) "$d/stbt-version.log" || fail "Wrong $d/stbt-version.log"
    [[ -f "$d/video.webm" ]] || fail "$d/video.webm not created"
    [[ -f "$d/thumbnail.jpg" ]] || fail "$d/thumbnail.jpg not created"
    if [[ -n "$commit" ]]; then
        [[ $(cat "$d/git-commit") == "$commit" ]] || fail "wrong $d/git-commit"
        [[ $(cat "$d/git-commit-sha") == "$expected_commit_sha" ]] \
            || fail "wrong $d/git-commit-sha"
    fi
    if [[ -n "$extra_column" ]]; then
        grep -q "$extra_column" "$d/extra-columns" || fail "extra column not in $d/extra-columns"
    fi
}

validate_html_report() {
    local d="$1" testname="$2" commit="$3" commit_sha="$4" extra_column="$5"
    local results_root=$(dirname "$d")

    [[ -f "$d/index.html" ]] || fail "$d/index.html not created"
    [[ -f "$results_root/index.html" ]] || fail "$results_root/index.html not created"
    grep -q "$testname" "$d/index.html" || fail "test name not in $d/index.html"
    grep -q "$testname" "$results_root/index.html" || fail "test name not in $results_root/index.html"
    if [[ -n "$commit" ]]; then
        grep -q "$commit" "$d/index.html" || fail "git commit not in $d/index.html"
        grep -q "$commit" "$results_root/index.html" || fail "git commit not in $results_root/index.html"
    fi
    if [[ -n "$extra_column" ]]; then
        grep -q "$extra_column" "$d/index.html" || fail "extra column not in $d/index.html"
        grep -q "$extra_column" "$results_root/index.html" || fail "extra column not in $results_root/index.html"
    fi
}

test_stbt_batch_run_once() {
    create_test_repo
    stbt batch run -1 -t "my label" tests/test.py ||
        fail "stbt batch run failed"

    local expected_commit="$(git -C tests describe --always)"
    local expected_commit_sha="$(git -C tests rev-parse HEAD)"

    validate_testrun_dir "latest-my label" test.py "$expected_commit" "$expected_commit_sha" "my label"
    validate_html_report "latest-my label" test.py "$expected_commit" "$expected_commit_sha" "my label"
}

test_that_stbt_batch_run_will_run_a_specific_function() {
    create_test_repo
    stbt batch run -o results -1 \
        tests/test_functions.py::test_that_this_test_is_run \
    || fail "Test failed"
    [ -e "results/current/touched" ] || fail "Test not run"
}

test_that_stbt_batch_run_runs_until_failure() {
    create_test_repo
    timeout 60 stbt batch run tests/test.py
    [[ $? -eq $timedout ]] && fail "'stbt batch run' timed out"

    ls -d ????-??-??_??.??.??* > testruns
    [[ $(cat testruns | wc -l) -eq 2 ]] || fail "Expected 2 test runs"
    first=$(head -1 testruns)
    grep -q success $first/failure-reason || fail "Expected 1st testrun to succeed"
    grep -q UITestError latest/failure-reason || fail "Expected 2nd testrun to fail with 'UITestError'"
    [[ -f $first/thumbnail.jpg ]] || fail "Expected successful testrun to create thumbnail"
    [[ ! -f $first/screenshot.png ]] || fail "Expected successful testrun to not create screenshot"
    [[ -f latest/thumbnail.jpg ]] || fail "Expected failed testrun to create thumbnail"
    [[ -f latest/screenshot.png ]] || fail "Expected failed testrun to create thumbnail"
}

test_that_stbt_batch_run_continues_after_uninteresting_failure() {
    create_test_repo
    timeout 120 stbt batch run -k tests/test.py
    [[ $? -eq $timedout ]] && fail "'run' timed out"

    ls -d ????-??-??_??.??.??* > testruns
    [[ $(cat testruns | wc -l) -eq 3 ]] || fail "Expected 3 test runs"
    grep -q success $(head -1 testruns)/failure-reason ||
        fail "Expected 1st testrun to succeed"
    grep -q UITestError $(sed -n 2p testruns)/failure-reason ||
        fail "Expected 2nd testrun to fail with 'UITestError'"
    grep -q MatchTimeout latest/failure-reason ||
        fail "Expected 3rd testrun to fail with 'MatchTimeout'"
}

test_stbt_batch_run_when_test_script_isnt_in_git_repo() {
    create_test_repo
    rm -rf tests/.git

    stbt batch run -1 tests/test.py || fail "stbt batch run failed"

    [[ $(cat latest/exit-status) == 0 ]] || fail "wrong latest/exit-status"
    [[ ! -f latest/git-commit ]] || fail "didn't expect to see latest/git-commit"
    grep -q tests/test.py latest/test-name || fail "wrong latest/test-name"
    grep -q tests/test.py latest/index.html || fail "test name not in latest/index.html"
    grep -q tests/test.py index.html || fail "test name not in index.html"
}

test_signalname() {
    sed -n '/^signalname()/,/^}/ p' "$srcdir"/stbt-batch.d/report \
        > signalname.sh &&
    . signalname.sh &&
    declare -f signalname || fail "'signalname' not defined"

    sleep 10 &
    pid=$!
    ( sleep 1; kill $pid ) &
    wait $pid
    ret=$?
    diff -u <(echo sigterm) <(signalname $((ret - 128)))
}

expect_runner_to_say() {
    for i in {1..100}; do
        cat log | grep -qF "$1" && return
        sleep 0.1
    done
    fail "Didn't find '$1' after 10 seconds"
}

test_stbt_batch_run_sigterm_once() {
    create_test_repo
    sleep=4 stbt batch run tests/test.py &
    runner=$!
    expect_runner_to_say "test.py ..."
    kill $runner
    expect_runner_to_say "waiting for current test to complete"
    wait $runner
    diff -u <(echo success) latest/failure-reason || fail "Bad failure-reason"
}

test_stbt_batch_run_sigterm_twice() {
    create_test_repo
    sleep=10 stbt batch run tests/test.py &
    runner=$!
    expect_runner_to_say "test.py ..."
    kill $runner
    expect_runner_to_say "waiting for current test to complete"
    kill $runner
    expect_runner_to_say "exiting"
    wait $runner
    diff -u <(echo "killed (sigterm)") latest/failure-reason ||
        fail "Bad failure-reason"
}

test_that_stbt_batch_run_passes_arguments_to_script() {
    create_test_repo
    stbt batch run -1 \
        tests/test.py "a b" c d -- \
        tests/test.py efg hij

    ls -d ????-??-??_??.??.??* > testruns
    assert grep 'Command-line argument: a b$' $(head -1 testruns)/stdout.log
    assert grep 'Command-line argument: c$' $(head -1 testruns)/stdout.log
    assert grep 'Command-line argument: d$' $(head -1 testruns)/stdout.log
    assert grep 'Command-line argument: efg$' latest/stdout.log
    assert grep 'Command-line argument: hij$' latest/stdout.log
    assert grep 'efg' index.html
    assert grep 'hij' index.html
    assert grep 'efg' latest/index.html
    assert grep 'hij' latest/index.html
}

test_stbt_batch_report_with_symlinks_for_each_testrun() {
    # Use case: After you've run `stbt batch run` several times from different
    # directories, you gather all results into a single report by symlinking
    # each testrun into a single directory.

    create_test_repo
    stbt batch run -1 tests/test.py &&
    mkdir new-report &&
    ( cd new-report; ln -s ../2* . ) ||
    fail "report directory structure setup failed"

    stbt batch report --html-only new-report/2* || return
    [[ -f new-report/index.html ]] || fail "new-report/index.html not created"
}

test_stbt_batch_run_with_custom_logging() {
    create_test_repo
    set_config batch.pre_run "$PWD/my-logger"
    set_config batch.post_run "$PWD/my-logger"

    cat > my-logger <<-'EOF'
	#!/bin/sh
	printf "%s time\t%s\n" $1 "$(date)" >> extra-columns
	EOF
    chmod u+x my-logger

    stbt batch run -1 tests/test.py

    grep -q '<th>start time</th>' index.html ||
        fail "'start time' missing from report"
    grep -q '<th>stop time</th>' index.html ||
        fail "'stop time' missing from report"
}

test_stbt_batch_run_with_custom_classifier() {
    create_test_repo
    set_config batch.classify "$PWD/my-classifier"

    cat > my-classifier <<-'EOF'
	#!/bin/bash
	if [[ $(cat exit-status) -ne 0 && $(cat test-name) =~ test.py ]];
	then
	    echo 'Intentional failure' > failure-reason
	fi
	EOF
    chmod u+x my-classifier

    timeout 60 stbt batch run tests/test.py
    [[ $? -eq $timedout ]] && fail "'stbt batch run' timed out"

    grep -q 'Intentional failure' index.html ||
        fail "Custom failure reason missing from report"
}

test_stbt_batch_run_without_html_reports() {
    create_test_repo
    set_config batch.classify "$PWD/my-classifier"
    cat > my-classifier <<-'EOF'
	#!/bin/bash
	touch my-classifier-ran
	EOF
    chmod u+x my-classifier

    timeout 60 stbt batch run -1 --no-html-report tests/test.py
    [[ $? -eq $timedout ]] && fail "'stbt batch run' timed out"

    validate_testrun_dir latest test.py
    ! [[ -f "latest/index.html" ]] || fail "latest/index.html shouldn't exist"
    ! [[ -f index.html ]] || fail "index.html shouldn't exist"

    # classify should still run.
    [[ -f latest/my-classifier-ran ]] || fail "Custom classifier didn't run"
}

test_stbt_batch_run_no_save_video_no_sink_pipeline() {
    do_test_stbt_batch_run_no_save_video --no-save-video ""
}

test_stbt_batch_run_no_save_video_fakesink() {
    do_test_stbt_batch_run_no_save_video --no-save-video fakesink
}

test_stbt_batch_run_no_sink_pipeline() {
    do_test_stbt_batch_run_no_save_video "" ""
}

do_test_stbt_batch_run_no_save_video() {
    local no_save_video="$1" sink_pipeline="$2"

    create_test_repo
    set_config global.sink_pipeline "$sink_pipeline"
    stbt batch run $no_save_video -1 -t "my label" tests/test.py ||
        fail "stbt batch run failed"

    local expected_commit="$(git -C tests describe --always)"
    local expected_commit_sha="$(git -C tests rev-parse HEAD)"

    case "$no_save_video" in
        --no-save-video)
            ! [ -e "latest-my label/video.webm" ] ||
            fail "Video was written even though it shouldn't have been";;
        *)
            [ -e "latest-my label/video.webm" ] ||
            fail "Video wasn't written even though it should have been";;
    esac

    # We still expect an HTML report even if a video is not available
    validate_html_report "latest-my label" test.py "$expected_commit" "$expected_commit_sha" "my label"
}

test_stbt_batch_run_with_custom_recovery_script() {
    create_test_repo
    set_config batch.recover "$PWD/my-recover"

    cat > my-recover <<-'EOF'
	#!/bin/sh
	touch powercycle.log
	EOF
    chmod u+x my-recover

    timeout 60 stbt batch run tests/test.py
    [[ $? -eq $timedout ]] && fail "'stbt batch run' timed out"

    grep -q '>powercycle.log</a>' latest/index.html ||
        fail "Custom recovery script's log missing from report"
}

test_stbt_batch_run_recovery_exit_status() {
    create_test_repo
    set_config batch.recover "$PWD/my-recover"

    cat > my-recover <<-'EOF'
	#!/bin/sh
	exit 1
	EOF
    chmod u+x my-recover

    timeout 60 stbt batch run -kk tests/test.py
    [[ $? -eq $timedout ]] && fail "'stbt batch run' timed out"

    ls -d ????-??-??_??.??.??* > testruns
    [[ $(cat testruns | wc -l) -eq 2 ]] || fail "Expected 2 test runs"
}

with_retry() {
    local count ret
    count="$1"; shift
    "$@"; ret=$?
    if [[ $count -gt 0 && $1 == curl && $ret -eq 7 ]];  # connection refused
    then
        sleep 1
        echo "Retrying ($count)..."
        with_retry $((count - 1)) "$@"
    else
        return $ret
    fi
}

test_stbt_batch_instaweb() {
    wait_for_report() {
        local parent=$1 children pid
        children=$(ps -o ppid= -o pid= | awk "\$1 == $parent {print \$2}")
        for pid in $children; do
            if ps -o command= -p $pid | grep -q report; then
                echo "Waiting for 'report' (pid $pid)"
                # Can't use `wait` because process isn't a direct child of this
                # shell. After finishing, `report` becomes a zombie process so
                # `ps` shows it as "(bash)" instead of "bash /path/to/report
                # ...".
                while ps -o command= -p $pid | grep -q report; do
                    sleep 0.1
                done
                echo "'report' completed"
                return
            fi
            wait_for_report $pid
        done
    }

    create_test_repo
    timeout 60 stbt batch run tests/test.py
    [[ $? -eq $timedout ]] && fail "'stbt batch run' timed out"
    rundir=$(ls -d 20* | tail -1)
    assert grep -q UITestError $rundir/failure-reason
    assert grep -q UITestError $rundir/index.html
    assert grep -q UITestError index.html

    stbt batch instaweb --debug 127.0.0.1:5787 &
    server=$!
    trap "killtree $server; wait $server" EXIT
    expect_runner_to_say 'Running on http://127.0.0.1:5787/'

    with_retry 5 curl --silent --show-error \
        -F 'value=manual failure reason' \
        http://127.0.0.1:5787/$rundir/failure-reason || fail 'Got HTTP failure'
    expect_runner_to_say "POST /$rundir/failure-reason"
    wait_for_report $server
    assert grep -q "manual failure reason" $rundir/failure-reason.manual
    assert grep -q "manual failure reason" $rundir/index.html
    assert grep -q "manual failure reason" index.html

    curl --silent --show-error \
        -F "value=UITestError: Not the system-under-test's fault" \
        http://127.0.0.1:5787/$rundir/failure-reason || fail 'Got HTTP failure'
    expect_runner_to_say "POST /$rundir/failure-reason"
    wait_for_report $server
    ! [[ -f $rundir/failure-reason.manual ]] ||
        fail "server didn't delete '$rundir/failure-reason.manual'"
    assert ! grep -q "manual failure reason" index.html
    assert ! grep -q "manual failure reason" $rundir/index.html

    curl --silent --show-error \
        -F 'value=Hi there £€' \
        http://127.0.0.1:5787/$rundir/notes || fail 'Got HTTP failure'
    expect_runner_to_say "POST /$rundir/notes"
    wait_for_report $server
    assert grep -q 'Hi there £€' $rundir/notes.manual
    assert grep -q 'Hi there £€' $rundir/index.html
    assert grep -q 'Hi there £€' index.html

    curl --silent --show-error -X POST \
        http://127.0.0.1:5787/$rundir/delete || fail 'Got HTTP failure'
    expect_runner_to_say "POST /$rundir/delete"
    wait_for_report $server
    ! [[ -f $rundir ]] || fail "server didn't hide '$rundir'"
    assert ! grep -q 'Hi there £€' index.html
}

test_that_stbt_batch_instaweb_shows_directory_listing() {
    mkdir my-test-session
    echo hi > my-test-session/index.html

    stbt batch instaweb --debug 127.0.0.1:5788 &
    server=$!
    trap "killtree $server; wait $server" EXIT
    expect_runner_to_say 'Running on http://127.0.0.1:5788/'

    with_retry 10 curl http://127.0.0.1:5788/ | grep my-test-session ||
        fail "Didn't find directory listing at '/'"
    diff -u my-test-session/index.html \
        <(curl -L http://127.0.0.1:5788/my-test-session) ||
        fail "Didn't find index.html at '/my-test-session'"
    diff -u my-test-session/index.html \
        <(curl http://127.0.0.1:5788/my-test-session/) ||
        fail "Didn't find index.html at '/my-test-session/'"
}

test_that_stbt_batch_run_isolates_stdin_of_user_hooks() {
    create_test_repo
    cat >my-logger <<-EOF
	read x
	[[ -z \$x ]] && echo STDIN=None || echo STDIN=\$x
	EOF
    chmod +x my-logger

    set_config batch.pre_run "$PWD/my-logger" &&

    stbt batch run -1 tests/test.py tests/test2.py
    cat log | grep -q "STDIN=None" || fail "Data in user script's STDIN"
    cat log | grep -q "test2.py ..." || fail "test2.py wasn't executed"
}

test_that_stbt_batch_run_exits_with_failure_if_any_test_fails() {
    create_test_repo
    stbt batch run -1 tests/test_success.py || fail "Test should succeed"
    cat */combined.log

    ! stbt batch run -1 tests/test_failure.py || fail "Test should fail"
    ! stbt batch run -1 tests/test_error.py || fail "Test should fail"

    ! stbt batch run -1 tests/test_success.py tests/test_failure.py \
        || fail "Test should fail"
    ! stbt batch run -1 tests/test_failure.py tests/test_success.py \
        || fail "Test should fail"
}

test_that_stbt_batch_propagates_exit_status_if_running_a_single_test() {
    create_test_repo
    stbt batch run -1 tests/test_success.py
    [ "$?" = 0 ] || fail "Test should succeed"

    stbt batch run -1 tests/test_failure.py
    [ "$?" = 1 ] || fail "Test should fail"

    stbt batch run -1 tests/test_error.py
    [ "$?" = 2 ] || fail "Test should error"
}

test_that_stbt_batch_reports_results_directory() {
    create_test_repo
    export STBT_TRACING_SOCKET=$PWD/stbt_tracing_socket
    socat -d -d -d -D -t10 UNIX-LISTEN:$STBT_TRACING_SOCKET,fork GOPEN:trace.log &
    SOCAT_PID=$!

    while ! [ -e "$PWD/stbt_tracing_socket" ]; do
      sleep 0.1
    done

    stbt batch run -1vv tests/test.py tests/test2.py \
        || fail "Tests should succeed"

    [ "$(grep active_results_directory trace.log | wc -l)" = 4 ] \
        || fail "active_results_directory not written"
    kill $SOCAT_PID

    cat trace.log
}

test_stbt_batch_output_dir() {
    create_test_repo
    stbt batch run -1 -o "my results" tests/test.py tests/test2.py \
        || fail "Tests should succeed"

    [[ -f "my results"/index.html ]] || fail "'my results/index.html' not created"
    ! [[ -f index.html ]] || fail "index.html created in current directory"
    grep -q test.py "my results"/*/test-name || fail "First test's results not in 'my results'"
    grep -q test2.py "my results"/*/test-name || fail "Second test's results not in 'my results'"

    validate_testrun_dir "my results/latest" test2.py
    validate_html_report "my results/latest" test2.py
}

test_printing_unicode_characters_in_scripts() {
    # This testcase documents the current behaviour when printing non-ascii
    # byte strings, which isn't necessarily the desired behaviour.

    which unbuffer &>/dev/null || skip "unbuffer is not installed"

    create_test_repo
    cat >tests/unicode.py <<-EOF
		# coding: utf-8
		import sys
		print u"  Röthlisberger"
		sys.stderr.write(u"  Röthlisberger\n")
		EOF

    cat >tests/utf8bytestring.py <<-EOF
		# coding: utf-8
		import sys
		s = u"  Röthlisberger\n".encode("utf-8")
		print s
		sys.stderr.write(s)
		EOF

    unset LC_ALL LC_CTYPE LANG

    # We use unbuffer here to provide a tty to `stbt run` to simulate
    # interactive use.

    echo "This should fail (non-utf8 capable tty):"
    ! LANG=C unbuffer bash -c 'stbt run tests/unicode.py' \
        || fail "stbt run should have failed to write to non-utf8 capable tty"

    echo "To terminal:" &&
    LANG=C.UTF-8 unbuffer bash -c 'stbt run tests/unicode.py' &&
    LANG=C.UTF-8 unbuffer bash -c 'stbt run tests/utf8bytestring.py' &&

    echo "stdout to /dev/null:" &&
    LANG=C.UTF-8 unbuffer bash -c 'stbt run tests/unicode.py >/dev/null' &&
    LANG=C.UTF-8 unbuffer bash -c 'stbt run tests/utf8bytestring.py >/dev/null' &&

    echo "stderr to /dev/null:" &&
    LANG=C.UTF-8 unbuffer bash -c 'stbt run tests/unicode.py 2>/dev/null' &&
    LANG=C.UTF-8 unbuffer bash -c 'stbt run tests/utf8bytestring.py 2>/dev/null' &&

    echo "stdout to file:" &&
    LANG=C.UTF-8 unbuffer bash -c 'stbt run tests/unicode.py >mylog1' &&
    LANG=C.UTF-8 unbuffer bash -c 'stbt run tests/utf8bytestring.py >mylog2' &&

    echo "stderr to file:" &&
    LANG=C.UTF-8 unbuffer bash -c 'stbt run tests/unicode.py 2>mylog3' &&
    LANG=C.UTF-8 unbuffer bash -c 'stbt run tests/utf8bytestring.py 2>mylog4' &&

    echo "stbt batch run:" &&
    stbt batch run -1 tests/unicode.py
    stbt batch run -1 tests/utf8bytestring.py
}

test_that_stbt_batch_run_can_print_exceptions_with_unicode_characters() {
    cat > test.py <<-EOF
	# coding: utf-8
	assert False, u"ü"
	EOF
    stbt batch run -1 test.py
    cat latest/combined.log latest/failure-reason
    grep -E 'FAIL: .*test.py: AssertionError: ü' latest/combined.log || fail
    grep 'assert False, u"ü"' latest/combined.log || fail
    grep 'AssertionError: ü' latest/failure-reason || fail
}

test_that_stbt_batch_run_can_print_exceptions_with_encoded_utf8_string() {
    cat > test.py <<-EOF
	# coding: utf-8
	assert False, u"ü".encode("utf-8")
	EOF
    stbt batch run -1 test.py
    cat latest/combined.log latest/failure-reason
    grep -E 'FAIL: .*test.py: AssertionError: ü' latest/combined.log || fail
    grep 'assert False, u"ü"' latest/combined.log || fail
    grep 'AssertionError: ü' latest/failure-reason || fail
}

test_that_tests_reading_from_stdin_dont_mess_up_batch_run_test_list() {
    cat >test.py <<-EOF
		import sys
		in_text = sys.stdin.read()
		assert in_text == "", "Stdin said \"%s\"" % in_text
		EOF

    stbt batch run -1 test.py test.py \
    || fail "Expected test to pass"

    ls -d ????-??-??_??.??.??* > testruns
    [[ $(cat testruns | wc -l) -eq 2 ]] || fail "Expected 2 test runs"
}

test_that_stbt_batch_failure_reason_shows_the_failing_assert_statement() {
    create_test_repo
    stbt batch run -1 tests/test_functions.py::test_that_asserts_the_impossible
    assert grep -q "AssertionError: assert 1 + 1 == 3" latest/failure-reason
}

test_that_stbt_batch_run_shuffle_runs_tests() {
    create_test_repo
    stbt batch run -1 --shuffle \
        tests/test_functions.py::test_that_does_nothing \
        tests/test_functions.py::test_that_this_test_is_run
    ls -d ????-??-??_??.??.??* > testruns
    [[ $(cat testruns | wc -l) -eq 2 ]] || fail "Expected 2 test runs"
}
