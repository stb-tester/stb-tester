test_auto_selftest_generate()
{
    cp -R "$testdir/auto-selftest-example-test-pack" pristine &&
    cp -R "pristine" "regenerated" &&
    rm -rf regenerated/selftest/auto_selftest &&
    cd regenerated &&
    stbt --with-experimental auto-selftest generate &&
    cd .. &&

    find . -name '*.pyc' -delete -o -name __pycache__ -delete &&
    diff -ur "pristine" "regenerated"
}

test_that_generated_auto_selftests_pass_as_doctests()
{
    PYTHONPATH=$srcdir python -m doctest \
        "$testdir/auto-selftest-example-test-pack/selftest/auto_selftest/tests/example_selftest.py"
}

cd_example_testpack()
{
    cp -R "$testdir/auto-selftest-example-test-pack" test-pack &&
    cd test-pack || fail "Test setup failed"
}


test_that_generated_auto_selftests_pass_stbt_auto_selftest_validate()
{
    cd_example_testpack &&
    stbt --with-experimental auto-selftest validate
}

test_that_no_auto_selftests_fail_stbt_auto_selftest_validate()
{
    cd_example_testpack &&
    rm -r selftest/auto_selftest &&
    ! stbt --with-experimental auto-selftest validate
}

test_that_new_auto_selftests_fail_stbt_auto_selftest_validate()
{
    cd_example_testpack &&
    touch selftest/auto_selftest/new.py &&
    ! stbt --with-experimental auto-selftest validate
}

test_that_missing_auto_selftests_fail_stbt_auto_selftest_validate()
{
    cd_example_testpack &&
    rm selftest/auto_selftest/tests/example_selftest.py &&
    ! stbt --with-experimental auto-selftest validate
}

test_that_modified_auto_selftests_fail_stbt_auto_selftest_validate()
{
    cd_example_testpack &&
    echo "pass" >>selftest/auto_selftest/tests/example_selftest.py &&
    ! stbt --with-experimental auto-selftest validate
}

test_that_no_screenshots_passes_stbt_auto_selftest_validate()
{
    cd_example_testpack &&
    rm -r selftest &&
    stbt --with-experimental auto-selftest validate
}

test_that_no_selftests_expressions_passes_stbt_auto_selftest_validate()
{
    cd_example_testpack &&
    rm -r tests/example.py tests/unicode_example.py selftest/auto_selftest \
          tests/subdir/subsubdir/subdir_example.py &&
    stbt --with-experimental auto-selftest validate
}

test_auto_selftest_caching()
{
    cd_example_testpack &&

    export XDG_CACHE_HOME=$PWD/cache

    # Regenerating the GStreamer plugin cache would have messed up our timing so
    # force it here:
    gst-inspect-1.0 &>/dev/null

    STBT_DISABLE_CACHING=1 /usr/bin/time --format=%e -o without_cache.time \
        stbt --with-experimental auto-selftest validate

    ! [ -e cache/stbt/cache.lmdb ] \
        || fail "Cache file created despite STBT_DISABLE_CACHING"

    /usr/bin/time --format=%e -o cold_cache.time \
        stbt --with-experimental auto-selftest validate \
        || fail "auto-selftest failed"

    [ -e cache/stbt/cache.lmdb ] || fail "Cache file not created"

    /usr/bin/time --format=%e -o hot_cache.time \
        stbt --with-experimental auto-selftest validate \
        || fail "auto-selftest failed"

    python -c "assert ($(<hot_cache.time) * 2) < $(<without_cache.time)" \
        || fail "caching isn't fast"
}
