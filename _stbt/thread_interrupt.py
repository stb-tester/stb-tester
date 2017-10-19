import functools
import itertools
import os
import threading
import time
import weakref
from collections import namedtuple
from contextlib import contextmanager


class ThreadInterrupt(BaseException):
    pass


_patching_mutex = threading.Lock()
_time_patched = False
_next_sleep = None


def patch():
    global _next_sleep, _time_patched

    with _patching_mutex:
        if not _time_patched:
            _next_sleep = time.sleep
            time.sleep = functools.wraps(time.sleep)(interruptible_sleep)
            _time_patched = True


_TimeOut = namedtuple('_TimeOut', 'now remaining')


def iter_timeout(timeout=10, now=None):
    if now is None:
        now = time.time()
    end_time = now + timeout
    while now < end_time:
        yield _TimeOut(now, end_time - now)
        now = time.time()


_global_condition = threading.Condition()
_threads_interrupted = weakref.WeakSet()
_condvars = {}
_counter = itertools.count()


def check_interrupt():
    with _global_condition:
        _check_interrupt_unlocked()


def _check_interrupt_unlocked():
    # This should be fast because _threads_interrupted will be an empty set the
    # vast majority of the time.
    if threading.current_thread() in _threads_interrupted:
        raise ThreadInterrupt()


def interruptible_sleep(seconds):
    with _global_condition:
        for t in iter_timeout(seconds):
            _check_interrupt_unlocked()
            _global_condition.wait(t.remaining)


def interrupt(thread):
    with _global_condition:
        _threads_interrupted.add(thread)
        condvars = list(_condvars)
        _global_condition.notify_all()
    for condvar in condvars:
        with condvar:
            condvar.notify_all()


class InterruptibleCondition(threading._Condition):  # pylint: disable=protected-access
    """
    It's a condition variable that can have it's `wait` interrupted by another
    thread.
    """
    def __init__(self, lock=None):
        super(InterruptibleCondition, self).__init__(lock)

    @contextmanager
    def lock_waitable(self):
        with self:
            yield self._wait

    def wait(self, timeout=None):
        assert False, "InterruptibleCondition - use lock_waitable"

    def _wait(self, timeout=None):
        """
        This can only be called with the lock held.  It's safe to call
        check_interrupt here because we don't call any function with
        _global_condition held.  _global_condition is a leaf lock. This means in
        terms of lock ordering that _global_condition is always ordered after
        self.
        """
        if timeout is None:
            timeout = 1e9
        with _global_condition:
            _check_interrupt_unlocked()
            n = _counter.next()
            _condvars[n] = self
        try:
            super(InterruptibleCondition, self).wait(timeout)
        finally:
            with _global_condition:
                del _condvars[n]


if not os.environ.get("STBT_DONT_PATCH_TIME"):
    patch()
