# Run with ./run-tests.sh

test_runner_once() {
    { "$srcdir"/extra/runner/run -1 -t my-label "$testdir"/test.py ||
        fail "runner/run failed"
    } | sed 's/^/runner: /'

    mv latest-my-label latest
    [[ -f latest/combined.log ]] || fail "latest/combined.log not created"
    [[ $(cat latest/exit-status) == 0 ]] || fail "wrong latest/exit-status"
    [[ -f latest/git-commit ]] || fail "latest/git-commit not created"
    [[ $(cat latest/test-name) =~ test.py ]] || fail "wrong latest/test-name"
    [[ -f latest/video.webm ]] || fail "latest/video.webm not created"
    [[ -f latest/index.html ]] || fail "latest/index.html not created"
    [[ -f index.html ]] || fail "index.html not created"
    grep -q test.py latest/index.html || fail "test name not in latest/index.html"
    grep -q 'tests/test.py' index.html || fail "test name not in index.html"
    grep -q my-label latest/index.html || fail "extra column not in latest/index.html"
    grep -q my-label index.html || fail "extra column not in index.html"
}

test_runner_runs_until_failure() {
    timeout 20 "$srcdir"/extra/runner/run "$testdir"/test.py
    [[ $? -eq $timedout ]] && fail "'run' timed out"

    ls -d ????-??-??_??.??.??* > testruns
    [[ $(cat testruns | wc -l) -eq 2 ]] || fail "Expected 2 test runs"
    grep -q success $(head -1 testruns)/failure-reason ||
        fail "Expected 1st testrun to succeed"
    grep -q UITestError latest/failure-reason ||
        fail "Expected 2nd testrun to fail with 'UITestError'"
}

test_runner_continues_after_uninteresting_failure() {
    timeout 30 "$srcdir"/extra/runner/run -k "$testdir"/test.py
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

test_runner_parse_test_args() {
    sed -n '/^parse_test_args() {/,/^}/ p' "$srcdir"/extra/runner/run \
        > parse_test_args.sh &&
    . parse_test_args.sh &&
    declare -f parse_test_args || fail "'parse_test_args' not defined"

    parse_test_args "test 1.py" test2.py test3.py |
    tee /dev/stderr |  # print to log
    while IFS=$'\t' read -a test; do echo "$test"; done > output1.log
    cat > expected1.log <<-EOF
	test 1.py
	test2.py
	test3.py
	EOF
    diff -u expected1.log output1.log ||
    fail "Unexpected output from 'parse_test_args' without '--'"

    parse_test_args test1.py "arg 1" arg2 -- test2.py arg -- test3.py |
    tee /dev/stderr |  # print to log
    while IFS=$'\t' read -a test; do
        for x in "${test[@]}"; do printf "'$x' "; done; printf "\n"
    done > output2.log
    cat > expected2.log <<-EOF
	'test1.py' 'arg 1' 'arg2' 
	'test2.py' 'arg' 
	'test3.py' 
	EOF
    diff -u expected2.log output2.log ||
    fail "Unexpected output from 'parse_test_args' with '--'"
}

test_runner_killtree() {
    sed -n '/^killtree()/,/^}/ p' "$srcdir"/extra/runner/run > killtree.sh &&
    . killtree.sh &&
    declare -f killtree || fail "'killtree' not defined"

    test_killtree  # in test-run-tests.sh
}

test_signalname() {
    sed -n '/^signalname()/,/^}/ p' "$srcdir"/extra/runner/report \
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

test_runner_sigint_once() {
    sleep=4 "$srcdir"/extra/runner/run "$testdir"/test.py &
    runner=$!
    expect_runner_to_say "test.py ..."
    kill $runner
    expect_runner_to_say "waiting for current test to complete"
    wait $runner
    diff -u <(echo success) latest/failure-reason || fail "Bad failure-reason"
}

test_runner_sigint_twice() {
    sleep=10 "$srcdir"/extra/runner/run "$testdir"/test.py &
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

test_runner_passes_arguments_to_script() {
    "$srcdir"/extra/runner/run \
        "$testdir"/test.py "a b" c d -- \
        "$testdir"/test.py efg hij

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

test_runner_report_with_symlinks_for_each_testrun() {
    # Use case: After you've run `runner/run` several times from different
    # directories, you gather all results into a single report by symlinking
    # each testrun into a single directory.

    "$srcdir"/extra/runner/run -1 "$testdir"/test.py &&
    mkdir new-report &&
    ( cd new-report; ln -s ../2* . ) ||
    fail "report directory structure setup failed"

    "$srcdir"/extra/runner/report --html-only new-report/2* || return
    [[ -f new-report/index.html ]] || fail "new-report/index.html not created"
}

test_runner_custom_logging() {
    cat "$testdir"/stbt.conf |
    sed -e "s,pre_run =,& $PWD/my-logger," \
        -e "s,post_run =,& $PWD/my-logger," > stbt.conf

    cat > my-logger <<-'EOF'
	#!/bin/sh
	printf "%s time\t%s\n" $1 "$(date)" >> extra-columns
	EOF
    chmod u+x my-logger

    export STBT_CONFIG_FILE="$PWD"/stbt.conf
    "$srcdir"/extra/runner/run -1 "$testdir"/test.py

    grep -q '<th>start time</th>' index.html ||
        fail "'start time' missing from report"
    grep -q '<th>stop time</th>' index.html ||
        fail "'stop time' missing from report"
}

test_runner_custom_classifier() {
    cat "$testdir"/stbt.conf |
    sed -e "s,classify =,& $PWD/my-classifier," > stbt.conf

    cat > my-classifier <<-'EOF'
	#!/bin/bash
	if [[ $(cat exit-status) -ne 0 && $(cat test-name) =~ tests/test.py ]];
	then
	    echo 'Intentional failure' > failure-reason
	fi
	EOF
    chmod u+x my-classifier

    export STBT_CONFIG_FILE="$PWD"/stbt.conf
    "$srcdir"/extra/runner/run "$testdir"/test.py

    grep -q 'Intentional failure' index.html ||
        fail "Custom failure reason missing from report"
}

test_runner_custom_recovery_script() {
    cat "$testdir"/stbt.conf |
    sed -e "s,recover =,& $PWD/my-recover," > stbt.conf

    cat > my-recover <<-'EOF'
	#!/bin/sh
	touch powercycle.log
	EOF
    chmod u+x my-recover

    export STBT_CONFIG_FILE="$PWD"/stbt.conf
    "$srcdir"/extra/runner/run "$testdir"/test.py

    grep -q '>powercycle.log</a>' latest/index.html ||
        fail "Custom recovery script's log missing from report"
}

test_runner_recovery_exit_status() {
    cat "$testdir"/stbt.conf |
    sed -e "s,recover =,& $PWD/my-recover," > stbt.conf

    cat > my-recover <<-'EOF'
	#!/bin/sh
	exit 1
	EOF
    chmod u+x my-recover

    export STBT_CONFIG_FILE="$PWD"/stbt.conf
    "$srcdir"/extra/runner/run -kk "$testdir"/test.py

    ls -d ????-??-??_??.??.??* > testruns
    [[ $(cat testruns | wc -l) -eq 2 ]] || fail "Expected 2 test runs"
}

test_runner_results_server() {
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

    "$srcdir"/extra/runner/run "$testdir"/test.py
    rundir=$(ls -d 20* | tail -1)
    assert grep -q UITestError $rundir/failure-reason
    assert grep -q UITestError $rundir/index.html
    assert grep -q UITestError index.html

    "$srcdir"/extra/runner/server --debug localhost:5787 &
    server=$!
    trap "killtree $server; wait $server" EXIT
    expect_runner_to_say 'Running on http://localhost:5787/'
    sleep 1

    curl --silent --show-error \
        -F 'value=manual failure reason' \
        http://localhost:5787/$rundir/failure-reason || fail 'Got HTTP failure'
    expect_runner_to_say "POST /$rundir/failure-reason"
    wait_for_report $server
    assert grep -q "manual failure reason" $rundir/failure-reason.manual
    assert grep -q "manual failure reason" $rundir/index.html
    assert grep -q "manual failure reason" index.html

    curl --silent --show-error \
        -F "value=UITestError: Not the system-under-test's fault" \
        http://localhost:5787/$rundir/failure-reason || fail 'Got HTTP failure'
    expect_runner_to_say "POST /$rundir/failure-reason"
    wait_for_report $server
    ! [[ -f $rundir/failure-reason.manual ]] ||
        fail "server didn't delete '$rundir/failure-reason.manual'"
    assert ! grep -q "manual failure reason" index.html
    assert ! grep -q "manual failure reason" $rundir/index.html

    curl --silent --show-error \
        -F 'value=Hi there £€' \
        http://localhost:5787/$rundir/notes || fail 'Got HTTP failure'
    expect_runner_to_say "POST /$rundir/notes"
    wait_for_report $server
    assert grep -q 'Hi there £€' $rundir/notes.manual
    assert grep -q 'Hi there £€' $rundir/index.html
    assert grep -q 'Hi there £€' index.html

    curl --silent --show-error -X POST \
        http://localhost:5787/$rundir/delete || fail 'Got HTTP failure'
    expect_runner_to_say "POST /$rundir/delete"
    wait_for_report $server
    ! [[ -f $rundir ]] || fail "server didn't hide '$rundir'"
    assert ! grep -q 'Hi there £€' index.html
}

test_runner_results_server_shows_directory_listing() {
    mkdir my-test-session
    echo hi > my-test-session/index.html

    "$srcdir"/extra/runner/server --debug localhost:5788 &
    server=$!
    trap "killtree $server; wait $server" EXIT
    expect_runner_to_say 'Running on http://localhost:5788/'
    sleep 1

    curl http://localhost:5788/ | grep my-test-session ||
        fail "Didn't find directory listing at '/'"
    diff -u my-test-session/index.html \
        <(curl -L http://localhost:5788/my-test-session) ||
        fail "Didn't find index.html at '/my-test-session'"
    diff -u my-test-session/index.html \
        <(curl http://localhost:5788/my-test-session/) ||
        fail "Didn't find index.html at '/my-test-session/'"
}

test_runner_isolates_stdin_of_user_hooks() {
    cat >my-logger <<-EOF
	read x
	[[ -z \$x ]] && echo STDIN=None || echo STDIN=\$x
	EOF
    chmod +x my-logger

    cat "$testdir"/stbt.conf | \
        sed -e "s,pre_run =,& $PWD/my-logger," >stbt.conf

    export STBT_CONFIG_FILE="$PWD"/stbt.conf
    "$srcdir"/extra/runner/run -1 "$testdir"/test.py "$testdir"/test2.py
    cat log | grep -q "STDIN=None" || fail "Data in user script's STDIN"
    cat log | grep -q "test2.py ..." || fail "test2.py wasn't executed"
}
