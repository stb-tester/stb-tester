# Run with ./run-tests.sh

test_that_readme_is_up_to_date() {
    cp -R "$srcdir" stb-tester &&
    cd stb-tester &&
    make update-api-docs ||
    fail "Failed to run 'update-api-docs'"

    diff -u "$srcdir"/README.rst README.rst ||
    fail "README.rst is not up to date; run 'make update-api-docs'"
}
