# Run with ./run-tests.sh

test_that_readme_is_up_to_date() {
    if git -C "$srcdir" describe --dirty | grep -q dirty; then
        skip "source directory has uncommitted changes"
    fi

    git clone "$srcdir" stb-tester &&
    cd stb-tester &&
    make update-api-docs ||
    fail "Failed to run 'update-api-docs'"

    [[ -z "$(git status --porcelain -- README.rst)" ]] || {
        git diff
        fail "README.rst is not up to date; run 'make update-api-docs'"
    }
}
