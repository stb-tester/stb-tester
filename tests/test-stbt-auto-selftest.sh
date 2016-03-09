test_auto_selftest_generate()
{
    cp -R "$testdir/auto-selftest-example-test-pack" pristine &&
    cp -R "pristine" "regenerated" &&
    rm -rf regenerated/selftest/auto_selftest &&
    cd regenerated &&
    stbt auto-selftest generate &&
    cd .. &&

    find . -name '*.pyc' -delete &&
    diff -ur "pristine" "regenerated"
}

test_that_generated_auto_selftests_pass_as_doctests()
{
    PYTHONPATH=$srcdir python -m doctest \
        "$testdir/auto-selftest-example-test-pack/selftest/auto_selftest/tests/example_selftest.py"
}
