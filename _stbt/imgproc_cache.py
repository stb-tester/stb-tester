"""
This file implements caching of expensive image processing operations for the
purposes of speeding up subsequent runs of stbt auto-selftest.

To enable caching, decorate the cachable function with `imgproc_cache.memoize`
and call the function within the scope of a `with imgproc_cache.cache():`
context manager. For now this is a private API but we intend to make it public
at some point so that users can add caching to any custom image-processing
functions in their test-packs.
"""

import functools
import inspect
import itertools
import json
import os
import sys
from contextlib import contextmanager
from itertools import zip_longest

import numpy

try:
    import lmdb
    from _stbt.xxhash import Xxhash64
except ImportError:
    lmdb = None

from _stbt.logging import ImageLogger
from _stbt.utils import mkdir_p, named_temporary_directory, scoped_curdir


MAX_CACHE_SIZE_BYTES = 1024 * 1024 * 1024  # 1GiB
_cache = None
_cache_full_warning = None
_enabled = False


default_filename = "%s/%s" % (
    os.environ.get("XDG_CACHE_HOME") or ("%s/.cache" % os.environ["HOME"]),
    "stbt/cache.lmdb")


@contextmanager
def setup_cache(filename=None):
    """Set up the cache. Typically called by stbt-run before running your test.

    This is safe to call if lmdb isn't installed; in that case it'll be a
    no-op.

    :param str filename: Defaults to $XDG_CACHE_HOME/stbt/cache.lmdb (or
        $HOME/.cache/stbt/cache.lmdb if XDG_CACHE_HOME isn't set).
    """
    if lmdb is None or os.environ.get('STBT_DISABLE_CACHING'):
        yield
        return

    global _cache
    global _cache_full_warning

    if filename is None:
        filename = default_filename
    mkdir_p(os.path.dirname(filename) or ".")
    with lmdb.open(filename, map_size=MAX_CACHE_SIZE_BYTES) as db:
        assert _cache is None
        try:
            _cache = db
            _cache_full_warning = False
            yield
        finally:
            _cache = None


@contextmanager
def enable_caching(enable=True):
    """Enable caching of all cachable image-processing operations.

    Note: This is not thread safe. To enable caching on a call-by-call basis
    pass ``use_cache=True`` when calling the memoized function.
    """

    global _enabled
    previous_value = _enabled
    try:
        _enabled = enable
        yield
    finally:
        _enabled = previous_value


def memoize(additional_fields=None):
    """
    A decorator to say that the results of a function should be cached.  This is
    used to short circuit expensive image processing functions like OCR.

    A hash is taken of all the decorated functions arguments and any additional
    fields specified to the decorator.  This is used as a key to retrieve a
    previously calculated result from a database on disk.

    **Constraints**

    * The decorated function's arguments must be simple JSON serialisable
      values or an image in the form of a numpy.ndarray.
    * The return value from the function must be JSON serialisable and should
      be round-trippable via JSON. This means that unicode objects should be
      returned rather than string objects.
    * For the sake of speed we use a non-cryptographic hash function.  This
      means someone could deliberately cause a hash-collision by carefully
      constructing arguments to your function.  Don't use memoize on functions
      where this could be a problem.
    * The input arguments are not stored on disk, just the hash is.  This means
      that the (in-memory) size of the input arguments will not have an effect
      on the disk usage and caching can be used on functions that take large
      amounts of data (such as video frames).
    * The full result of calling the function is stored on disk, so the (in
      memory) size of the result have an impact on disk usage. It's best not to
      memoize functions that return large amounts of data like video frames or
      intermediate frames in some video-processing chain.
    * This means that memoize works best on functions that take large amounts of
      data (like frames of video) and boil it down to a small amount of data
      (like a MatchResult or OCR text).

    This decorator adds the paramater ``use_cache`` to the decorated function.
    Set it to True to enable caching on a call-by-call basis.

    This function is not a part of the stbt public API and may change without
    warning in future releases.  We hope to stabilise it in the future so users
    can use it with their custom image-processing functions.
    """
    def decorator(f):
        func_key = json.dumps([f.__name__, additional_fields],
                              sort_keys=True)

        @functools.wraps(f)
        def inner(*args, **kwargs):
            use_cache = kwargs.pop("use_cache", None)
            try:
                if _cache is None or (not _enabled and not use_cache):
                    raise NotCachable()
                full_kwargs = inspect.getcallargs(f, *args, **kwargs)  # pylint:disable=deprecated-method
                key = _cache_hash((func_key, full_kwargs))
            except NotCachable:
                return f(*args, **kwargs)

            with _cache.begin() as txn:
                out = txn.get(key)
            if out is not None:
                return json.loads(out)
            output = f(**full_kwargs)
            _cache_put(key, output)
            return output

        return inner
    return decorator


def memoize_iterator(additional_fields=None):
    """
    A decorator like `imgproc_cache.memoize`, but for functions that return an
    iterator.
    """

    def decorator(f):
        func_key = json.dumps([f.__name__, additional_fields],
                              sort_keys=True)

        @functools.wraps(f)
        def inner(*args, **kwargs):
            use_cache = kwargs.pop("use_cache", None)
            try:
                if _cache is None or (not _enabled and not use_cache):
                    raise NotCachable()
                full_kwargs = inspect.getcallargs(f, *args, **kwargs)  # pylint:disable=deprecated-method
                key = _cache_hash((func_key, full_kwargs))
            except NotCachable:
                for x in f(*args, **kwargs):
                    yield x
                return

            for i in itertools.count():
                with _cache.begin() as txn:
                    out = txn.get(key + str(i).encode())
                if out is None:
                    break
                out_, stop_ = json.loads(out)
                if stop_:
                    return
                yield out_

            skip = i  # pylint:disable=undefined-loop-variable
            it = f(**full_kwargs)
            for i in itertools.count():
                try:
                    output = next(it)
                    if i >= skip:
                        _cache_put(key + str(i).encode(), [output, None])
                        yield output
                except StopIteration:
                    _cache_put(key + str(i).encode(), [None, "StopIteration"])
                    return

        return inner
    return decorator


def _cache_put(key, value):
    try:
        with _cache.begin(write=True) as txn:
            txn.put(key, json.dumps(value).encode("utf-8"))
    except (lmdb.MapFullError, lmdb.DiskError):
        global _cache_full_warning
        if not _cache_full_warning:
            sys.stderr.write(
                "Image processing cache is full.  This will "
                "cause degraded performance.  Consider "
                "deleting the cache file (%s) to purge old "
                "results\n" % _cache.path())
            _cache_full_warning = True


class NotCachable(Exception):
    pass


class _ArgsEncoder(json.JSONEncoder):
    def default(self, o):  # pylint:disable=method-hidden
        from _stbt.imgutils import Color
        from _stbt.match import MatchParameters
        if isinstance(o, ImageLogger):
            if o.enabled:
                raise NotCachable()
            return None
        elif isinstance(o, set):
            return sorted(o)
        elif isinstance(o, Color):
            return o.hexstring
        elif isinstance(o, MatchParameters):
            return {
                "match_method": o.match_method.value,
                "match_threshold": o.match_threshold,
                "confirm_method": o.confirm_method.value,
                "confirm_threshold": o.confirm_threshold,
                "erode_passes": o.erode_passes}
        elif isinstance(o, numpy.ndarray):
            h = Xxhash64()
            h.update(numpy.ascontiguousarray(o).data)
            return (o.shape, h.hexdigest())
        else:
            json.JSONEncoder.default(self, o)


def _cache_hash(value):
    # type: (...) -> bytes
    h = Xxhash64()

    class HashWriter():
        def write(self, data):
            if isinstance(data, str):
                data = data.encode("utf-8")
            h.update(data)
            return len(data)

    json.dump(value, HashWriter(), cls=_ArgsEncoder, sort_keys=True)
    return h.digest()


def test_that_cache_is_disabled_when_debug_match():
    # debug logging is a side effect that the cache cannot reproduce
    import stbt_core as stbt
    import _stbt.logging
    with scoped_curdir() as srcdir, setup_cache('cache.lmdb'), enable_caching():
        stbt.match(srcdir + '/tests/red-black.png',
                   frame=numpy.zeros((720, 1280, 3), dtype=numpy.uint8))
        assert not os.path.exists('stbt-debug')

        with _stbt.logging.scoped_debug_level(2):
            stbt.match(srcdir + '/tests/red-black.png',
                       frame=numpy.zeros((720, 1280, 3), dtype=numpy.uint8))
        assert os.path.exists('stbt-debug')


def _fields_eq(a, b, fields):
    for x in fields:
        assert type(getattr(a, x)) == type(getattr(b, x))  # pylint:disable=unidiomatic-typecheck
        if isinstance(getattr(a, x), numpy.ndarray):
            assert (getattr(a, x) == getattr(b, x)).all()
        else:
            assert getattr(a, x) == getattr(b, x)


def _check_cache_behaviour(func):
    from timeit import Timer

    timer = Timer(func)
    uncached_result = func()
    uncached_time = min(timer.repeat(10, number=1))

    with named_temporary_directory() as tmpdir, \
            setup_cache(tmpdir), enable_caching():
        # Prime the cache
        func()
        cached_time = min(timer.repeat(10, number=1))
        cached_result = func()

    print("%s with cache: %s" % (func.__name__, cached_time))
    print("%s without cache: %s" % (func.__name__, uncached_time))

    return cached_time, uncached_time, cached_result, uncached_result


def test_memoize_types():
    # `memoize` isn't guaranteed to return the exact type that was returned,
    # because it goes through JSON serialisation. This is OK because `memoize`
    # is only used to cache the results of internal stbt functions, and the
    # (internal) users of memoize ensure that they handle the cached return
    # values correctly. Here we test that, at least, common arguments don't
    # cause any serialisation problems.
    import stbt_core as stbt

    @memoize()
    def f(arg):
        return arg

    @memoize()
    def f2(arg):
        return str(arg)  # stbt.Color is not JSON serialisable

    with named_temporary_directory() as tmpdir, \
            setup_cache(tmpdir), enable_caching():

        assert f(stbt.Region(1, 2, 3, 4)) == stbt.Region(1, 2, 3, 4)
        assert f(stbt.Region(1, 2, 3, 4)) == [1, 2, 4, 6]

        assert f(stbt.Size(1, 2)) == stbt.Size(1, 2)
        assert f(stbt.Size(1, 2)) == [1, 2]

        assert f(stbt.Position(1, 2)) == [1, 2]
        assert f(stbt.Position(3, 4)) == stbt.Position(3, 4)
        assert f(stbt.Position(3, 4)) == [3, 4]

        assert f2(stbt.Color("#ff7f00")) == "Color('#ff7f00')"
        assert f2(stbt.Color("#ff7f00")) == "Color('#ff7f00')"


def test_memoize_iterator():
    counter = [0]

    @memoize_iterator()
    def cached_function(_arg):
        for x in range(10):
            counter[0] += 1
            yield x

    with named_temporary_directory() as tmpdir, \
            setup_cache(tmpdir), enable_caching():

        uncached = list(itertools.islice(cached_function(1), 5))
        assert uncached == list(range(5))
        assert counter[0] == 5

        cached = list(itertools.islice(cached_function(1), 5))
        assert cached == list(range(5))
        assert counter[0] == 5

        partially_cached = list(itertools.islice(cached_function(1), 10))
        assert partially_cached == list(range(10))
        assert counter[0] == 15

        partially_cached = list(cached_function(1))
        assert partially_cached == list(range(10))
        assert counter[0] == 25

        cached = list(cached_function(1))
        assert cached == list(range(10))
        assert counter[0] == 25

        uncached = list(cached_function(2))
        assert uncached == list(range(10))
        assert counter[0] == 35


def test_memoize_iterator_on_empty_iterator():
    counter = [0]

    @memoize_iterator()
    def cached_function():
        counter[0] += 1
        if False:  # pylint:disable=using-constant-test
            yield

    with named_temporary_directory() as tmpdir, \
            setup_cache(tmpdir), enable_caching():

        uncached = list(cached_function())
        assert uncached == []
        assert counter[0] == 1

        cached = list(cached_function())
        assert cached == []
        assert counter[0] == 1


def test_that_cache_speeds_up_match():
    import stbt_core as stbt
    black = numpy.zeros((1440, 2560, 3), dtype=numpy.uint8)

    def match():
        return stbt.match('tests/red-black.png', frame=black)

    cached_time, uncached_time, cached_result, uncached_result = (
        _check_cache_behaviour(match))

    assert uncached_time > (cached_time * 4)
    _fields_eq(cached_result, uncached_result,
               ['match', 'region', 'first_pass_result', 'frame', 'image'])


def test_that_cache_speeds_up_match_all():
    import stbt_core as stbt
    import cv2

    frame = cv2.imread('tests/buttons.png')

    def match_all():
        return list(stbt.match_all('tests/button.png', frame=frame))

    cached_time, uncached_time, cached_result, uncached_result = (
        _check_cache_behaviour(match_all))

    assert uncached_time > (cached_time * 2)
    assert len(uncached_result) == 6
    for cached, uncached in zip_longest(cached_result, uncached_result):
        _fields_eq(cached, uncached,
                   ['match', 'region', 'first_pass_result', 'frame', 'image'])


def test_that_cache_speeds_up_ocr():
    import stbt_core as stbt
    import cv2

    frame = cv2.imread('tests/red-black.png')

    def ocr():
        return stbt.ocr(frame=frame)

    cached_time, uncached_time, cached_result, uncached_result = (
        _check_cache_behaviour(ocr))

    assert uncached_time > (cached_time * 10)
    assert type(cached_result) == type(uncached_result)  # pylint:disable=unidiomatic-typecheck

    assert cached_result == uncached_result


def test_that_cache_speeds_up_match_text():
    import stbt_core as stbt
    import cv2

    frame = cv2.imread('tests/red-black.png')

    def match_text():
        return stbt.match_text("RED", frame=frame)

    cached_time, uncached_time, cached_result, uncached_result = (
        _check_cache_behaviour(match_text))

    assert uncached_time > (cached_time * 10)

    print(cached_result)

    _fields_eq(cached_result, uncached_result,
               ['match', 'region', 'frame', 'text'])
