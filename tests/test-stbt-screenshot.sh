# Run with ./run-tests.sh

test_that_stbt_screenshot_saves_file_to_disk() {
    rm -f screenshot.png
    stbt-screenshot && [ -f screenshot.png ] && rm -f screenshot.png
}
