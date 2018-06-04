cd_example_testpack()
{
    cp -R "$testdir/auto-selftest-example-test-pack" test-pack &&
    cd test-pack || fail "Test setup failed"
}

check_generated_files()
{
    diff -ur --exclude="*.pyc" --exclude=__pycache__ \
        "$testdir"/auto-selftest-example-test-pack/selftest/auto_selftest \
        ./selftest/auto_selftest || fail "Unexpected changes to selftest files"
}

test_auto_selftest_generate()
{
    cd_example_testpack &&
    stbt auto-selftest generate &&
    diff -ur --exclude="*.pyc" --exclude=__pycache__ \
        "$testdir"/auto-selftest-example-test-pack .
}

test_auto_selftest_generate_first_time() {
    cd_example_testpack &&
    rm -rf selftest/auto_selftest &&
    stbt auto-selftest generate &&
    diff -ur --exclude="*.pyc" --exclude=__pycache__ \
        "$testdir"/auto-selftest-example-test-pack .
}

test_that_generated_auto_selftests_pass_as_doctests()
{
    PYTHONPATH=$srcdir python -m doctest \
        "$testdir/auto-selftest-example-test-pack/selftest/auto_selftest/tests/example_selftest.py"
}

test_that_generated_auto_selftests_pass_stbt_auto_selftest_validate()
{
    cd_example_testpack &&
    stbt auto-selftest validate
}

test_that_no_auto_selftests_fail_stbt_auto_selftest_validate()
{
    cd_example_testpack &&
    rm -r selftest/auto_selftest &&
    ! stbt auto-selftest validate
}

test_that_new_auto_selftests_fail_stbt_auto_selftest_validate()
{
    cd_example_testpack &&
    touch selftest/auto_selftest/new.py &&
    ! stbt auto-selftest validate
}

test_that_missing_auto_selftests_fail_stbt_auto_selftest_validate()
{
    cd_example_testpack &&
    rm selftest/auto_selftest/tests/example_selftest.py &&
    ! stbt auto-selftest validate
}

test_that_modified_auto_selftests_fail_stbt_auto_selftest_validate()
{
    cd_example_testpack &&
    echo "pass" >>selftest/auto_selftest/tests/example_selftest.py &&
    ! stbt auto-selftest validate
}

test_that_no_screenshots_passes_stbt_auto_selftest_validate()
{
    cd_example_testpack &&
    rm -r selftest &&
    stbt auto-selftest validate
}

test_that_no_selftests_expressions_passes_stbt_auto_selftest_validate()
{
    cd_example_testpack &&
    rm -r tests_in_root.py \
          tests/example.py tests/unicode_example.py \
          tests/subdir/subsubdir/subdir_example.py \
          selftest/auto_selftest &&
    stbt auto-selftest validate
}

test_auto_selftest_caching()
{
    cd_example_testpack &&

    export XDG_CACHE_HOME=$PWD/cache

    # Regenerating the GStreamer plugin cache would have messed up our timing so
    # force it here:
    gst-inspect-1.0 &>/dev/null

    STBT_DISABLE_CACHING=1 /usr/bin/time --format=%e -o without_cache.time \
        stbt auto-selftest validate

    ! [ -e cache/stbt/cache.lmdb ] \
        || fail "Cache file created despite STBT_DISABLE_CACHING"

    /usr/bin/time --format=%e -o cold_cache.time \
        stbt auto-selftest validate \
        || fail "auto-selftest failed"

    [ -e cache/stbt/cache.lmdb ] || fail "Cache file not created"

    /usr/bin/time --format=%e -o hot_cache.time \
        stbt auto-selftest validate \
        || fail "auto-selftest failed"

    python -c "assert ($(<hot_cache.time) * 2) < $(<without_cache.time)" \
        || fail "caching isn't fast"
}

test_auto_selftest_generate_with_single_source_file() {
    cd_example_testpack &&
    sed '/^class FalseyFrameObject/,/return/ s/return False/return True/' \
        tests/example.py | sponge tests/example.py &&
    stbt auto-selftest generate tests/example.py &&
    grep -q 'FalseyFrameObject(is_visible=True)' \
        selftest/auto_selftest/tests/example_selftest.py \
        || fail "Didn't regenerate selftest"
    diff -ur --exclude="*.pyc" --exclude=__pycache__ \
        --exclude=example.py --exclude=example_selftest.py \
        "$testdir"/auto-selftest-example-test-pack . \
        || fail "Changed other selftest files"
}

test_auto_selftest_generate_first_time_with_single_source_file() {
    cd_example_testpack &&
    rm -rf selftest/auto_selftest &&
    stbt auto-selftest generate tests/example.py &&
    diff -u selftest/auto_selftest/tests/example_selftest.py \
         "$testdir"/auto-selftest-example-test-pack/selftest/auto_selftest/tests/example_selftest.py
}

test_auto_selftest_generate_with_single_invalid_source_file() {
    cd_example_testpack &&
    ! stbt auto-selftest generate tests/syntax_error.py
}

test_auto_selftest_generate_with_single_empty_source_file() {
    cd_example_testpack &&
    stbt auto-selftest generate tests/example_with_no_tests.py &> stbt.log \
        || { cat stbt.log; return 1; }

    check_generated_files

    grep -q "warning: 'tests/example_with_no_tests.py' doesn't define any selftests" stbt.log \
        || fail "Didn't find expected warning in 'stbt auto-selftest' output"
}

test_auto_selftest_generate_with_single_empty_source_file_deletes_selftest() {
    cd_example_testpack &&
    echo "" > tests/example.py &&
    stbt auto-selftest generate tests/example.py ||
        fail "stbt auto-selftest failed"

    ! [[ -e selftest/auto_selftest/tests/example_selftest.py ]] ||
        fail "example_selftest.py wasn't deleted"
}

test_auto_selftest_generate_with_two_source_files() {
    cd_example_testpack &&
    rm selftest/auto_selftest/tests/example_selftest.py \
       selftest/auto_selftest/tests/unicode_example_selftest.py &&
    stbt auto-selftest generate tests/example.py \
                                tests/unicode_example.py &&
    check_generated_files
}

test_auto_selftest_generate_with_two_source_files_one_of_which_is_empty() {
    cd_example_testpack &&
    rm selftest/auto_selftest/tests/example_selftest.py &&
    stbt auto-selftest generate tests/example_with_no_tests.py \
                                tests/example.py &&
    check_generated_files
}
