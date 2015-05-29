"""Utilities for registering failures to be reported by `stbt-run`.

Users can use these function to communicate with `stbt-run` that a failure has
been encountered during test execution but that it will be worked around and so
the failure should be reported as a test summary on test completion.

Metadata is stored per-registered failure including an exit status which
`stbt-run` can use to determine its own return code.

Example::

    stbt.press('OK')
    if stbt.match('error-message.png'):
        stbt.push_test_error('my-bug-id', 'Error message was seen')


    exception = None
    for attempt in range(2):
        stbt.press('MENU')
        try:
            stbt.wait_for_match('menu.png')
        except stbt.MatchTimeout as e:
            exception = e
        else:
            if attempt == 1:
                stbt.push_test_failure(
                    'SOMEBUG-123', 'Menu requires 2 presses',
                    screenshot=e.screenshot)
            break
    else:
        if exception is not None:
            raise exception
"""

import datetime
import traceback

from _stbt.logging import ddebug, debug

import stbt

_registered_failures = []


def push_test_failure(
        classification, description, screenshot=None, exception=None):
    """Register a test failure to be reported by `stbt-run` on test conclusion.

    :param str classification:
        A short name by which to refer to the failure. For example, a bugzilla
        ticket ID.
    :param str description:
        A description or details of the classification.
    :param numpy.ndarray screenshot:
        An image (in OpenCV format) to be saved as `classification`.png when
        `stbt-run` concludes. Defaults to None, which results in a frame being
        saved from the given exception or captured from live.
    :param Exception exception:
        An Exception object which `stbt-run` can raise directly if only one
        failure was registered during test execution, and is also given as
        details of the failure in the summary output. Defaults to None.
    """
    _push_failure(
        classification, description,
        exit_status=1, screenshot=screenshot, exception=exception)


def push_test_error(
        classification, description, screenshot=None, exception=None):
    """Register a test error to be reported by `stbt-run` on test conclusion.

    :param str classification:
        A short name by which to refer to the failure. For example, a bugzilla
        ticket ID.
    :param str description:
        A description or details of the classification.
    :param numpy.ndarray screenshot:
        An image (in OpenCV format) to be saved as `classification`.png when
        `stbt-run` concludes. Defaults to None, which results in a frame being
        saved from the given exception or captured from live.
    :param Exception exception:
        An Exception object which `stbt-run` can raise directly if only one
        failure was registered during test execution, and is also given as
        details of the failure in the summary output. Defaults to None.
    """
    _push_failure(
        classification, description,
        exit_status=2, screenshot=screenshot, exception=exception)


def get_registered_failures():
    """Return a list of test failures and errors which have been registered.

    The failures and errors are registered with `push_test_failure` and
    `push_test_error` respectively.
    """
    return _registered_failures


class _Failure(object):
    """Metadata container for a failure encountered in a test script.

    See `_push_failure` for params.
    """

    def __init__(
            self, classification, description, exit_status, screenshot,
            exception):
        self.classification = classification
        self.description = description
        self.exit_status = exit_status
        if screenshot is not None:
            self.screenshot = screenshot
        elif hasattr(exception, 'screenshot') and \
                exception.screenshot is not None:
            self.screenshot = exception.screenshot
        else:
            self.screenshot = stbt.get_frame()
        self.exception = exception
        self.timestamp = datetime.datetime.now()

    def __repr__(self):
        return "%s: (@%s) %s - %s" % (
            "Failure" if self.exit_status == 1 else "Error",
            self.timestamp, self.classification, self.description)


def _push_failure(
        classification, description, exit_status=1, screenshot=None,
        exception=None):
    """Register a failure to be reported by `stbt-run` on test conclusion.

    :param int exit_status:
        `stbt-run` uses this to determine its return code. See `stbt-run -h`.

    See `push_test_failure` or `push_test_error` for details of the other
    parameters.
    """
    failure = _Failure(
        classification, description, exit_status, screenshot, exception)

    debug(''.join([
        "Registering %s '%s' " % (
            "failure" if exit_status == 1 else "error", failure),
        "with %s screenshot " % ("a" if screenshot is not None else "no"),
        "and%s" % (
            " no exception." if exception is None
            else " this exception:\n\t%s" % traceback.format_exc())
    ]))

    _registered_failures.append(failure)
    ddebug(
        "There are now %d registered failures." % len(_registered_failures))
