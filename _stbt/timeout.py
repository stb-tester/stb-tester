import functools
import threading
import time


def timeout(duration=None, raise_=True):
    """Can be used as a decorator or a contextmanager."""
    return _Timeout(duration, raise_)


def sleep(duration):
    """A timeout aware version of time.sleep."""
    with Timeout(duration, raise_=False):
        while True:
            time.sleep(check_timeout())


def sleep_until(end_time):
    with Timeout(end_time=end_time, raise_=False):
        while True:
            time.sleep(check_timeout())


def check_timeout(now=None):
    """Raises an exception on timeout, otherwise returns the amount of time left
    until the next timeout."""
    try:
        stack = _TL.stack
    except AttributeError:
        return float('inf')
    if now is None:
        now = time.time()
    stack_level = None
    for n, t in enumerate(stack):
        if t.end_time < now:
            t._timed_out = True  # pylint: disable=protected-access
            if stack_level is None:
                stack_level = n
    if stack_level is not None:
        raise TimeoutRewind(stack_level, now)
    else:
        return min(stack).end_time - now


class StillRunning(Exception):
    pass


class TimeoutRewind(BaseException):
    """This should only be caught by the contextmanager that set up the
    timeout so it derives from BaseException.  Think of it as equivalent to
    GeneratorExit or similar."""
    def __init__(self, stack_level, check_time):
        super(TimeoutRewind, self).__init__()
        self.stack_level = stack_level
        self.check_time = check_time


class Timeout(Exception):
    def __init__(self, message, check_time):
        super(Timeout, self).__init__(message)
        self.check_time = check_time


_TL = threading.local()


class _Timeout(object):
    def __init__(self, duration=None, message=None, end_time=None, raise_=True):
        self.duration = duration
        self.message = message
        self.raise_ = raise_

        self.end_time = end_time
        self._stack_pos = None

        # This is set in check_timeout:
        self._timed_out = None

    # Allow using as a decorator:
    def __call__(self, func):
        if self.message is None:
            self.message = "during %s" % func.__name__
        @functools.wraps(func)
        def inner(*args, **kwargs):
            with self:
                func(*args, **kwargs)
        return inner

    def __cmp__(self, other):
        return cmp(self.end_time, other.end_time)

    def __enter__(self):
        if self.duration is None:
        if self.duration is None and self.end_time is None:
            self.end_time = float('inf')
            return self

        if self.end_time is None:
            self.end_time = time.time() + duration

        try:
            stack = _TL.stack
        except AttributeError:
            stack = []
            _TL.stack = stack

        self._stack_pos = len(stack)
        stack.append(self)
        return self

    def __exit__(self, _exc_type, exc_value, traceback):
        if self.duration is None:
            self._timed_out = False
            return None

        stack = _TL.stack
        assert self._stack_pos == len(stack)
        top_of_stack = stack.pop()
        assert top_of_stack is self
        if isinstance(exc_value, TimeoutRewind) and \
                exc_value.stack_level == self._stack_pos:
            if self.raise_:
                raise Timeout, \
                      Timeout("Timeout", exc_value.check_time), \
                      traceback
            else:
                # Suppress the exception:
                return True
        else:
            return None

    def timed_out(self):
        if self._timed_out is None:
            raise StillRunning("Still running")
        return self._timed_out
