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
    grep -q '>tests/test.py</a>' index.html || fail "test name not in index.html"
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
    timeout 20 "$srcdir"/extra/runner/run -k "$testdir"/test.py
    [[ $? -eq $timedout ]] && fail "'run' timed out"

    ls -d ????-??-??_??.??.??* > testruns
    [[ $(cat testruns | wc -l) -eq 3 ]] || fail "Expected 3 test runs"
    grep -q success $(head -1 testruns)/failure-reason ||
        fail "Expected 1st testrun to succeed"
    grep -q UITestError $(sed -n 2p testruns)/failure-reason ||
        fail "Expected 2nd testrun to fail with 'UITestError'"
    grep -q "Didn't find match" latest/failure-reason ||
        fail "Expected 3rd testrun to fail with 'Didn't find match'"
}

test_killtree() {
    sed -n '/^killtree()/,/^}/ p' "$srcdir"/extra/runner/run > killtree.sh &&
    . killtree.sh &&
    declare -f killtree || fail "'killtree' not defined"

    cat > killtree-test1.sh <<-EOF
	sh killtree-test2.sh
	EOF
    cat > killtree-test2.sh <<-EOF
	sh killtree-test3.sh
	EOF
    cat > killtree-test3.sh <<-EOF
	sleep 60
	EOF

    waitfor() { while ! ps -f | grep -v grep | grep "$1"; do sleep 0.1; done; }

    sh killtree-test1.sh &
    pid=$!
    waitfor killtree-test3.sh
    killtree $!
    ps -f
    ! ps -f | grep -v grep | grep -q killtree-test3.sh ||
    fail "child process 'killtree-test3.sh' still running"
}

expect_runner_to_say() {
    for i in {1..10}; do
        cat log | grep -qF "$1" && return
        sleep 0.1
    done
    fail "Didn't find '$1' after 1 second"
}

test_runner_sigint_once() {
    sleep=2 "$srcdir"/extra/runner/run "$testdir"/test.py &
    runner=$!
    expect_runner_to_say "test.py..."
    kill $runner
    expect_runner_to_say "waiting for current test to complete"
    wait $runner
    diff -u <(echo success) latest/failure-reason || fail "Bad failure-reason"
}

test_runner_sigint_twice() {
    sleep=2 "$srcdir"/extra/runner/run "$testdir"/test.py &
    runner=$!
    expect_runner_to_say "test.py..."
    kill $runner
    expect_runner_to_say "waiting for current test to complete"
    kill $runner
    expect_runner_to_say "exiting"
    wait $runner
    diff -u <(echo "killed (sigterm)") latest/failure-reason ||
        fail "Bad failure-reason"
}
