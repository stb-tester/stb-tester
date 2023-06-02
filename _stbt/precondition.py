"""
Copyright 2014 YouView TV Ltd.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).
"""

import traceback
from contextlib import contextmanager

from .logging import debug
from .types import UITestError, UITestFailure


class PreconditionError(UITestError):
    """Exception raised by `as_precondition`."""
    def __init__(self, message, original_exception):
        super(PreconditionError, self).__init__()
        self.message = message
        self.original_exception = original_exception
        self.screenshot = None

    def __str__(self):
        return (
            "Didn't meet precondition '%s' (original exception was: %s)"
            % (self.message, self.original_exception))


@contextmanager
def as_precondition(message):
    """Context manager that replaces test failures with test errors.

    Stb-tester's reports show test failures (that is, `UITestFailure` or
    `AssertionError` exceptions) as red results, and test errors (that is,
    unhandled exceptions of any other type) as yellow results. Note that
    `wait_for_match`, `wait_for_motion`, and similar functions raise a
    `UITestFailure` when they detect a failure. By running such functions
    inside an `as_precondition` context, any `UITestFailure` or
    `AssertionError` exceptions they raise will be caught, and a
    `PreconditionError` will be raised instead.

    When running a single testcase hundreds or thousands of times to reproduce
    an intermittent defect, it is helpful to mark unrelated failures as test
    errors (yellow) rather than test failures (red), so that you can focus on
    diagnosing the failures that are most likely to be the particular defect
    you are looking for. For more details see `Test failures vs. errors
    <http://stb-tester.com/preconditions>`__.

    :param str message:
        A description of the precondition. Word this positively: "Channels
        tuned", not "Failed to tune channels".

    :raises:
        `PreconditionError` if the wrapped code block raises a `UITestFailure`
        or `AssertionError`.

    Example::

        def test_that_the_on_screen_id_is_shown_after_booting():
            channel = 100

            with stbt.as_precondition("Tuned to channel %s" % channel):
                mainmenu.close_any_open_menu()
                channels.goto_channel(channel)
                power.cold_reboot()
                assert channels.is_on_channel(channel)

            stbt.wait_for_match("on-screen-id.png")

    """
    try:
        yield
    except (UITestFailure, AssertionError) as original:
        debug("stbt.as_precondition caught a %s exception and will "
              "re-raise it as PreconditionError.\nOriginal exception was:\n%s"
              % (type(original).__name__, traceback.format_exc()))
        exc = PreconditionError(message, original)
        if hasattr(original, 'screenshot'):
            exc.screenshot = original.screenshot  # pylint:disable=no-member
        raise exc
