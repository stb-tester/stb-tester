# Run with ./run-tests.sh

skip_if_no_docker() {
    which docker >/dev/null 2>&1 || skip "docker is not installed"
    docker version >/dev/null 2>&1 || skip "docker does not work"
}

load_test_pack() {
    skip_if_no_docker
    if [ -n "$2" ]; then
        outdir=$2
    else
        outdir=.
    fi

    mkdir -p "$outdir"
    cp -r "$testdir/test-packs/$1" "$outdir" &&
    cd "$outdir/$1" || fail "Loading test pack $1 failed"
}

test_stbt_docker_fails_with_no_test_pack() {
    skip_if_no_docker

    ! stbt docker true || fail
}

test_stbt_docker_exec_runs_command_with_no_setup_script() {
    load_test_pack empty-test-pack
    stbt docker echo -n hello >output || fail "Command should have succeeded"

    [ "$(cat output)" = "hello" ] || fail "Command not run"
}

test_stbt_docker_exec_runs_command_with_setup_script() {
    load_test_pack setup-script
    stbt docker echo -n hello >output || fail "Command should have succeeded"

    [ "$(cat output)" = "hello" ] || fail "Command not run"
}

test_that_stbt_docker_exec_fails_with_bad_test_pack()
{
    load_test_pack bad-setup-script
    ! stbt docker true || fail "Command should have failed"
}

test_your_files_are_available_in_stbt_docker() {
    load_test_pack empty-test-pack
    stbt docker test -e config/stbt.conf || fail "Command should have succeeded"
}

test_that_path_within_container_is_same_as_outside() {
    load_test_pack empty-test-pack

    stbt docker bash -c '[ $PWD = /var/lib/stbt/test-pack ]' \
    || fail "Directory doesnt match"

    cd config
    stbt docker bash -c '[ $PWD = /var/lib/stbt/test-pack/config ]' \
    || fail "Directory doesnt match"
}

test_that_docker_opts_passes_arguments_through_to_docker_run() {
    load_test_pack empty-test-pack
    export DOCKER_OPTS="-e HELLO=goodbye\\ cruel\\ world"
    stbt docker bash -c 'echo -e $HELLO >output'

    [ "$(cat output)" = "goodbye cruel world" ] \
    || fail "DOCKER_OPTS has no effect"
}

test_that_with_different_uid_we_still_have_permissions_to_files() {
    [ -n "$TRAVIS" ] || skip "Test will only run on Travis because it involves changing system state"

    sudo adduser --gecos "" test-user &&
    sudo chmod 777 ~test-user &&
    sudo cp $testdir/../stbt-docker /usr/bin/stbt-docker &&
    sudo chmod a+rx /usr/bin/stbt-docker &&
    sudo adduser test-user docker &&
    load_test_pack setup-script ~test-user &&
    sudo chown -R test-user:test-user . &&
    sudo chmod 700 ~test-user || fail "Test setup failed"

    sudo -u test-user bash <<-'EOF'
		stbt-docker bash -c 'touch hello'
		[ "$(ls -l hello | awk '{ print $3 }')" == 'test-user' ]
		EOF
    [ "$?" == 0 ] || fail "UID switching broken"
}
