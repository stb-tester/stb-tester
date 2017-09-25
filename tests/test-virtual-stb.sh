# Run with ./run-tests.sh

rotate_py=$testdir/vstb-example-html5/tests/rotate.py &&

with_html5_vstb()
{
    which chromium-browser &>/dev/null || skip "chromium-browser not installed"

    stbt virtual-stb run --background \
        "$@" $testdir/vstb-example-html5/run.sh &&
    trap "stbt virtual-stb stop -f" EXIT
}

test_that_virtual_stb_configures_stb_tester_for_testing_virtual_stbs()
{
    with_html5_vstb --x-keymap=$testdir/vstb-example-html5/key-mapping.conf

    stbt run $rotate_py::wait_for_vstb_startup &&
    stbt run $rotate_py::test_that_image_is_rotated_by_arrows &&
    stbt run $rotate_py::test_that_image_returns_to_normal_on_OK &&
    stbt run $rotate_py::test_that_custom_key_is_recognised
}

test_that_virtual_stb_works_without_keymap_file()
{
    with_html5_vstb

    stbt run $rotate_py::wait_for_vstb_startup &&
    stbt run $rotate_py::test_that_image_is_rotated_by_arrows &&
    ! stbt run $rotate_py::test_that_custom_key_is_recognised
}

test_that_virtual_stb_stop_clears_up()
{
    with_html5_vstb &&
    VSTB_PID="$(stbt config global.vstb_pid)"
    kill -0 "$VSTB_PID" || fail "setup failed"
    stbt virtual-stb stop || fail "stop failed"
    ! kill -0 "$VSTB_PID" || fail "virtual-stb wasn't killed"
    [ -z "$(stbt config global.vstb_pid)" ] || fail "Config wasn't reset"
}

# Regression test:
test_that_virtual_stb_works_with_keymap_file_at_relative_path()
{
    cp $testdir/vstb-example-html5/key-mapping.conf . &&
    with_html5_vstb --x-keymap=key-mapping.conf &&

    mkdir subdir &&
    cd subdir &&
    stbt run $rotate_py::wait_for_vstb_startup &&
    stbt run $rotate_py::test_that_image_is_rotated_by_arrows
}
