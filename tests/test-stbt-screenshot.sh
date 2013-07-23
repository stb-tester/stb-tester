# Run with ./run-tests.sh

test_that_stbt_screenshot_saves_file_to_disk() {
    cd "$scratchdir" &&
    stbt-screenshot &&
    [ -f screenshot.png ]
}

test_that_stbt_screenshot_obeys_filename_arg() {
    cd "$scratchdir" &&
    stbt-screenshot "my screenshot.png" &&
    [ -f "my screenshot.png" ]
}
