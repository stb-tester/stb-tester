# Run with ./run-tests.sh

: ${stbt_lint:=stbt lint}

assert_lint_log() {
    cat > lint.expected
    diff -u lint.expected <(grep -v "Using config file" lint.log) \
    || fail "see diff above"
}

test_that_stbt_lint_passes_existing_images() {
    cat > test.py <<-EOF &&
	import stbt_core as stbt
	stbt.wait_for_match('$testdir/videotestsrc-redblue.png')
	EOF
    $stbt_lint --errors-only test.py
}

test_that_stbt_lint_fails_nonexistent_image() {
    cat > test.py <<-EOF &&
	import stbt_core as stbt
	stbt.wait_for_match('idontexist.png')
	EOF
    $stbt_lint --errors-only test.py &> lint.log
    assert_lint_log <<-EOF
	************* Module test
	E:  2,20: Image "idontexist.png" not found on disk (stbt-missing-image)
	EOF
}

test_that_stbt_lint_ignores_generated_image_names() {
    cat > test.py <<-EOF &&
	import os
	import re
	import stbt_core as stbt
	from os.path import join
	var = 'idontexist'
	stbt.wait_for_match(var + '.png')
	stbt.wait_for_match('%s.png' % var)
	stbt.wait_for_match(f"{var} - selected.png")
	stbt.wait_for_match(os.path.join('directory', 'idontexist.png'))
	stbt.wait_for_match(join('directory', 'idontexist.png'))
	var.replace('idontexist', 'idontexist.png')
	re.sub(r'idontexist$', 'idontexist.png', var)
	EOF
    $stbt_lint --errors-only test.py
}

test_that_stbt_lint_ignores_regular_expressions() {
    cat > test.py <<-EOF &&
	import re
	re.match(r'.*/(.*)\.png', '')
	EOF
    $stbt_lint --errors-only test.py
}

test_that_stbt_lint_ignores_images_created_by_the_stbt_script() {
    cat > test.py <<-EOF &&
	import cv2, stbt_core as stbt
	stbt.save_frame(stbt.get_frame(), 'i-dont-exist-yet.png')
	cv2.imwrite('neither-do-i.png', stbt.get_frame())  # pylint:disable=no-member
	
	from cv2 import imwrite  # pylint:disable=no-name-in-module
	from stbt_core import save_frame
	save_frame(stbt.get_frame(), 'i-dont-exist-yet.png')
	imwrite('neither-do-i.png', stbt.get_frame())
	EOF
    $stbt_lint --errors-only --extension-pkg-whitelist=cv2 test.py
}

test_that_stbt_lint_ignores_multiline_image_name() {
    cat > test.py <<-EOF &&
	import subprocess
	subprocess.check_call("""set -e
	    tvservice -e "CEA 16"  # 1080p60
	    sudo fbi -T 1 -noverbose original.png
	    sudo fbi -T 2 -noverbose original.png""")
	EOF
    $stbt_lint --errors-only test.py
}

test_that_stbt_lint_ignores_image_urls() {
    cat > test.py <<-EOF &&
	def urlopen(x): pass
	urlopen("http://example.com/image.png")
	EOF
    $stbt_lint --errors-only test.py
}

test_that_stbt_lint_reports_uncommitted_images() {
    mkdir -p repo/tests/images
    touch repo/tests/images/reference.png
    cat > repo/tests/test.py <<-EOF
	import stbt_core as stbt
	assert stbt.match("images/reference.png")
	EOF
    cd repo
    $stbt_lint --errors-only tests/test.py ||
        fail "checker should be disabled because we're not in a git repo"

    git init .
    $stbt_lint --errors-only tests/test.py &> lint.log
    assert_lint_log <<-EOF
	************* Module test
	E:  2,18: Image "tests/images/reference.png" not committed to git (stbt-uncommitted-image)
	EOF

    (cd tests && $stbt_lint --errors-only test.py) &> lint.log
    assert_lint_log <<-EOF
	************* Module test
	E:  2,18: Image "images/reference.png" not committed to git (stbt-uncommitted-image)
	EOF

    git add tests/images/reference.png
    $stbt_lint --errors-only tests/test.py || fail "stbt-lint should succeed"

    (cd tests && $stbt_lint --errors-only test.py) ||
        fail "stbt-lint should succeed from subdirectory too"
}

test_pylint_plugin_on_itself() {
    # It should work on arbitrary python files, so that you can just enable it
    # as a pylint plugin across your entire project, not just for stbt scripts.
    [ -f "$srcdir"/stbt/pylint_plugin.py ] || skip 'Running outside $srcdir'
    $stbt_lint --errors-only "$srcdir"/stbt/pylint_plugin.py
}

test_that_stbt_lint_checks_uses_of_stbt_return_values() {
    cat > test.py <<-EOF &&
	import re, stbt_core as stbt
	from stbt_core import (is_screen_black, match, match_text, ocr, press,
	                       press_and_wait, wait_until)
	
	def test_something():
	    assert wait_until(lambda: True)
	    some_var = wait_until(lambda: True)
	    if wait_until(lambda: True): pass
	    wait_until(lambda: True)
	    stbt.wait_until(lambda: True)
	    something_else_that_ends_in_wait_until()  # pylint:disable=undefined-variable
	    assert match('$testdir/videotestsrc-redblue.png')
	    match('$testdir/videotestsrc-redblue.png')
	    re.match('foo', 'bah')
	    press('KEY_OK')
	    is_screen_black()
	    match_text('hello')
	    ocr()
	    press_and_wait("KEY_DOWN")
	    stbt.press_and_wait("KEY_DOWN")
	    assert press_and_wait("KEY_DOWN")
	    assert stbt.press_and_wait("KEY_DOWN")
	EOF
    $stbt_lint --errors-only test.py > lint.log

    assert_lint_log <<-'EOF'
	************* Module test
	E:  9, 4: "wait_until" return value not used (missing "assert"?) (stbt-unused-return-value)
	E: 10, 4: "stbt.wait_until" return value not used (missing "assert"?) (stbt-unused-return-value)
	E: 13, 4: "match" return value not used (missing "assert"?) (stbt-unused-return-value)
	E: 16, 4: "is_screen_black" return value not used (missing "assert"?) (stbt-unused-return-value)
	E: 17, 4: "match_text" return value not used (missing "assert"?) (stbt-unused-return-value)
	E: 18, 4: "ocr" return value not used (missing "assert"?) (stbt-unused-return-value)
	E: 19, 4: "press_and_wait" return value not used (missing "assert"?) (stbt-unused-return-value)
	E: 20, 4: "stbt.press_and_wait" return value not used (missing "assert"?) (stbt-unused-return-value)
	EOF
}

test_that_stbt_lint_checks_that_wait_until_argument_is_callable() {
    cat > test.py <<-EOF &&
	import functools
	from functools import partial
	from stbt_core import is_screen_black, press, wait_until
	
	def return_a_function():
	    return lambda: True
	
	def test_something():
	    press('KEY_POWER')
	    assert wait_until(is_screen_black)
	    assert wait_until(is_screen_black())
	    assert wait_until(return_a_function())
	    assert wait_until(return_a_function()())
	    assert wait_until(lambda: True)
	    assert wait_until((lambda: True)())
	    assert wait_until(functools.partial(lambda x: True, x=3))
	    assert wait_until(functools.partial(lambda x: True, x=3)())
	    assert wait_until(partial(lambda x: True, x=3))  # Pylint can't infer functools.partial. pylint:disable=stbt-wait-until-callable
	    assert wait_until(partial(lambda x: True, x=3)())
	EOF
    $stbt_lint --errors-only test.py > lint.log

    assert_lint_log <<-'EOF'
	************* Module test
	E: 11,11: "wait_until" argument "is_screen_black()" isn't callable (stbt-wait-until-callable)
	E: 13,11: "wait_until" argument "return_a_function()()" isn't callable (stbt-wait-until-callable)
	E: 15,11: "wait_until" argument "(lambda: True)()" isn't callable (stbt-wait-until-callable)
	E: 17,11: "wait_until" argument "functools.partial(lambda x: True, x=3)()" isn't callable (stbt-wait-until-callable)
	E: 19,11: "wait_until" argument "partial(lambda x: True, x=3)()" isn't callable (stbt-wait-until-callable)
	EOF
}

test_that_stbt_lint_checks_frameobjects() {
    cat > test.py <<-EOF
	import stbt_core as stbt
	
	def find_boxes(frame=None):
	    pass
	
	class Button(stbt.FrameObject):
	    pass
	
	class ModalDialog(stbt.FrameObject):
	    @property
	    def is_visible(self):
	        return find_boxes() and Button()
	
	class ErrorDialog(ModalDialog):
	    @property
	    def is_visible(self):
	        return bool(
	            stbt.match("videotestsrc-redblue.png") and
	            stbt.match_text("Error") and
	            not stbt.is_screen_black())
	
	    @property
	    def text(self):
	        return stbt.ocr()
	
	    @property
	    def another(self):
	        assert stbt.press_and_wait("KEY_RIGHT")
	        stbt.press("KEY_OK")
	        f = stbt.get_frame()
	        m = stbt.match("videotestsrc-redblue.png", frame=f)
	        return (m and
	                stbt.match_text("Error",
	                                frame=stbt.get_frame()) and
	                stbt.match_text("Error",
	                                stbt.get_frame()))
	
	class Good(stbt.FrameObject):
	    @property
	    def is_visible(self):
	        return find_boxes(self._frame) and Button(self._frame)
	
	    @property
	    def property1(self):
	        return bool(stbt.match("videotestsrc-redblue.png", self._frame))
	
	    @property
	    def property2(self):
	        return bool(stbt.match("videotestsrc-redblue.png",
	                               frame=self._frame))
	
	    def not_a_property(self):
	        if not bool(stbt.match("videotestsrc-redblue.png")):
	            stbt.press("KEY_OK")
	            return stbt.wait_until(
	                lambda: stbt.match("videotestsrc-redblue.png"))
	
	def my_test():
	    page = Good()
	    page.refresh()
	    page = page.refresh()
	EOF
    cp "$testdir/videotestsrc-redblue.png" .
    $stbt_lint --errors-only test.py > lint.log

    cat > expected.log <<-'EOF'
	************* Module test
	E: 12,15: "find_boxes()" missing "frame" argument (stbt-frame-object-missing-frame)
	E: 12,32: "Button()" missing "frame" argument (stbt-frame-object-missing-frame)
	E: 18,12: "stbt.match('videotestsrc-redblue.png')" missing "frame" argument (stbt-frame-object-missing-frame)
	E: 19,12: "stbt.match_text('Error')" missing "frame" argument (stbt-frame-object-missing-frame)
	E: 20,16: "stbt.is_screen_black()" missing "frame" argument (stbt-frame-object-missing-frame)
	E: 24,15: "stbt.ocr()" missing "frame" argument (stbt-frame-object-missing-frame)
	E: 28,15: FrameObject properties must not use "stbt.press_and_wait" (stbt-frame-object-property-press)
	E: 29, 8: FrameObject properties must not use "stbt.press" (stbt-frame-object-property-press)
	E: 30,12: FrameObject properties must use "self._frame", not "get_frame()" (stbt-frame-object-get-frame)
	E: 34,38: FrameObject properties must use "self._frame", not "get_frame()" (stbt-frame-object-get-frame)
	E: 36,32: FrameObject properties must use "self._frame", not "get_frame()" (stbt-frame-object-get-frame)
	E: 60, 4: FrameObject "refresh()" doesn't modify "page" instance (stbt-frame-object-refresh)
	EOF
    assert_lint_log < expected.log

    # Also test `match` instead of `stbt.match` (etc).
    sed -e 's/^import stbt_core as stbt$/from stbt_core import FrameObject, get_frame, is_screen_black, match, match_text, ocr, press, press_and_wait, wait_until/' \
        -e 's/stbt\.//g' \
        -i test.py expected.log
    $stbt_lint --errors-only test.py > lint.log
    assert_lint_log < expected.log
}

test_that_stbt_lint_ignores_astroid_inference_exceptions() {
    cat > test.py <<-EOF
	import stbt_core as stbt
	assert stbt.wait_until(InfoPage)
	EOF
    $stbt_lint --errors-only test.py > lint.log

    assert_lint_log <<-'EOF'
	************* Module test
	E:  2, 7: "wait_until" argument "InfoPage" isn't callable (stbt-wait-until-callable)
	E:  2,23: Undefined variable 'InfoPage' (undefined-variable)
	EOF
}

test_that_stbt_lint_warns_on_assert_true() {
    cat > test.py <<-EOF
	assert True
	assert True, "My message"
	EOF
    $stbt_lint --errors-only test.py > lint.log

    assert_lint_log <<-'EOF'
	************* Module test
	E:  1, 0: "assert True" has no effect (stbt-assert-true)
	E:  2, 0: "assert True" has no effect (stbt-assert-true)
	EOF
}

test_that_stbt_lint_understands_assert_false() {
    cat > test.py <<-EOF
	def moo():
	    assert False
	    print("Hi there")
	
	
	def cow(a):
	    if a:
	        return 5
	    # This checks that we've fixed pylint's false positive warning
	    # about inconsistent-return-statements ("Either all return
	    # statements in a function should return an expression, or none of
	    # them should").
	    assert False, "My Message"
	EOF
    $stbt_lint --disable=missing-docstring,invalid-name --score=no test.py > lint.log

    assert_lint_log <<-'EOF'
	************* Module test
	W:  3, 4: Unreachable code (unreachable)
	EOF
}
