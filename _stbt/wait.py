"""Copyright 2015-2019 Stb-tester.com Ltd."""

from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function

import functools
import inspect

from .logging import debug

try:
    from inspect import getfullargspec as getargspec
except ImportError:  # Python 2
    from inspect import getargspec


def wait_until(callable_, timeout_secs=10, interval_secs=0, predicate=None,
               stable_secs=0):
    """Wait until a condition becomes true, or until a timeout.

    Calls ``callable_`` repeatedly (with a delay of ``interval_secs`` seconds
    between successive calls) until it succeeds (that is, it returns a
    `truthy`_ value) or until ``timeout_secs`` seconds have passed.

    .. _truthy: https://docs.python.org/3.6/library/stdtypes.html#truth-value-testing

    :param callable_: any Python callable (such as a function or a lambda
        expression) with no arguments, or with a single argument called
        ``frame``.

    :type timeout_secs: int or float, in seconds
    :param timeout_secs: After this timeout elapses, ``wait_until`` will return
        the last value that ``callable_`` returned, even if it's falsey.

    :type interval_secs: int or float, in seconds
    :param interval_secs: Delay between successive invocations of ``callable_``.

    :param predicate: A function that takes a single value. It will be given
        the return value from ``callable_``. The return value of *this* function
        will then be used to determine truthiness. If the predicate test
        succeeds, ``wait_until`` will still return the original value from
        ``callable_``, not the predicate value.

    :type stable_secs: int or float, in seconds
    :param stable_secs: Wait for ``callable_``'s return value to remain the same
        (as determined by ``==``) for this duration before returning. If
        ``predicate`` is also given, the values returned from ``predicate``
        will be compared.

    :returns: The return value from ``callable_`` (which will be truthy if it
        succeeded, or falsey if ``wait_until`` timed out). If the value was
        truthy when the timeout was reached but it failed the ``predicate`` or
        ``stable_secs`` conditions (if any) then ``wait_until`` returns
        ``None``.

    After you send a remote-control signal to the device-under-test it usually
    takes a few frames to react, so a test script like this would probably
    fail::

        stbt.press("KEY_EPG")
        assert stbt.match("guide.png")

    Instead, use this::

        import stbt
        from stbt import wait_until

        stbt.press("KEY_EPG")
        assert wait_until(lambda: stbt.match("guide.png"))

    ``wait_until`` allows composing more complex conditions, such as::

        # Wait until something disappears:
        assert wait_until(lambda: not stbt.match("xyz.png"))

        # Assert that something doesn't appear within 10 seconds:
        assert not wait_until(lambda: stbt.match("xyz.png"))

        # Assert that two images are present at the same time:
        assert wait_until(lambda: stbt.match("a.png") and stbt.match("b.png"))

        # Wait but don't raise an exception if the image isn't present:
        if not wait_until(lambda: stbt.match("xyz.png")):
            do_something_else()

        # Wait for a menu selection to change. Here ``Menu`` is a `FrameObject`
        # subclass with a property called `selection` that returns the name of
        # the currently-selected menu item. The return value (``menu``) is an
        # instance of ``Menu``.
        menu = wait_until(Menu, predicate=lambda x: x.selection == "Home")

        # Wait for a match to stabilise position, returning the first stable
        # match. Used in performance measurements, for example to wait for a
        # selection highlight to finish moving:
        keypress = stbt.press("KEY_DOWN")
        match_result = wait_until(lambda: stbt.match("selection.png"),
                                  predicate=lambda x: x and x.region,
                                  stable_secs=2)
        assert match_result
        match_time = match_result.time  # this is the first stable frame
        print("Transition took %s seconds" % (match_time - keypress.end_time))

    Changed in v32: The ``callable_`` function can optionally take a parameter
    called ``frame``.
    """
    import time

    if predicate is None:
        predicate = lambda x: x

    if (inspect.isfunction(callable_) and
            "frame" in getargspec(callable_).args):  # pylint:disable=deprecated-method
        import stbt
        frames = stbt.frames()
        f = callable_
        callable_ = lambda: f(frame=next(frames))

    stable_value = None
    stable_predicate_value = None
    expiry_time = time.time() + timeout_secs

    while True:
        t = time.time()
        value = callable_()
        predicate_value = predicate(value)

        if stable_secs:
            if predicate_value != stable_predicate_value:
                stable_since = t
                stable_value = value
                stable_predicate_value = predicate_value
            if predicate_value and t - stable_since >= stable_secs:
                debug("wait_until succeeded: %s"
                      % _callable_description(callable_))
                return stable_value
        else:
            if predicate_value:
                debug("wait_until succeeded: %s"
                      % _callable_description(callable_))
                return value

        if t >= expiry_time:
            debug("wait_until timed out after %s seconds: %s"
                  % (timeout_secs, _callable_description(callable_)))
            if not value:
                return value  # it's falsey
            else:
                return None  # must have failed stable_secs or predicate checks

        time.sleep(interval_secs)


def _callable_description(callable_):
    """Helper to provide nicer debug output when `wait_until` fails.

    >>> _callable_description(wait_until)
    'wait_until'
    >>> _callable_description(
    ...     lambda: stbt.press("OK"))
    '    lambda: stbt.press("OK"))\\n'
    >>> _callable_description(functools.partial(eval, globals={}))
    'eval'
    >>> _callable_description(
    ...     functools.partial(
    ...         functools.partial(eval, globals={}),
    ...         locals={}))
    'eval'
    >>> class T(object):
    ...     def __call__(self): return True;
    >>> _callable_description(T())
    '<_stbt.wait.T object at 0x...>'
    """
    if hasattr(callable_, "__name__"):
        name = callable_.__name__
        if name == "<lambda>":
            try:
                name = inspect.getsource(callable_)
            except IOError:
                pass
        return name
    elif isinstance(callable_, functools.partial):
        return _callable_description(callable_.func)
    else:
        return repr(callable_)
