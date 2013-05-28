# Run with ./run-tests.sh

test_that_stbt_screenshot_saves_file_to_disk() {
    cd "$scratchdir" &&
    stbt-screenshot &&
    [ -f screenshot.png ]
}
