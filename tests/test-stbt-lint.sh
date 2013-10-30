# Run with ./run-tests.sh

test_that_stbt_lint_passes_existing_images() {
    cat > test.py <<-EOF &&
	import stbt
	stbt.wait_for_match('$testdir/videotestsrc-redblue.png')
	EOF
    stbt-lint --errors-only test.py
}

test_that_stbt_lint_fails_nonexistent_image() {
    cat > test.py <<-EOF &&
	import stbt
	stbt.wait_for_match('idontexist.png')
	EOF
    ! stbt-lint --errors-only test.py
}

test_that_stbt_lint_ignores_generated_image_names() {
    cat > test.py <<-EOF &&
	import os
	import stbt
	var = 'idontexist'
	stbt.wait_for_match(var + '.png')
	stbt.wait_for_match('%s.png' % var)
	stbt.wait_for_match(os.path.join('directory', 'idontexist.png'))
	EOF
    stbt-lint --errors-only test.py
}

test_that_stbt_lint_ignores_regular_expressions() {
    cat > test.py <<-EOF &&
	import re
	re.match(r'.*/(.*)\.png', '')
	EOF
    stbt-lint --errors-only test.py
}

test_that_stbt_lint_ignores_images_created_by_the_stbt_script() {
    cat > test.py <<-EOF &&
	import stbt
	stbt.save_frame(stbt.get_frame(), 'i-dont-exist-yet.png')
	EOF
    stbt-lint --errors-only test.py
}

test_pylint_plugin_on_itself() {
    # It should work on arbitrary python files, so that you can just enable it
    # as a pylint plugin across your entire project, not just for stbt scripts.
    stbt-lint --errors-only "$srcdir"/stbt_pylint_plugin.py
}
