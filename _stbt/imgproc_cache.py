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
import json
import os
import sys
from contextlib import contextmanager

import numpy

from _stbt.gst_utils import Gst, numpy_from_sample
from _stbt.logging import ImageLogger
from _stbt.utils import mkdir_p, named_temporary_directory

# Our embedded version of lmdb does `import lmdb` itself.  Work around this with
# sys.path:
sys.path.append(os.path.dirname(__file__))
import _stbt.lmdb as lmdb  # isort:skip
del sys.path[-1]


MAX_CACHE_SIZE_BYTES = 1024 * 1024 * 1024  # 1GiB
_cache = None
_cache_full_warning = None


@contextmanager
def cache(filename=None):
    if os.environ.get('STBT_DISABLE_CACHING'):
        yield
        return

    global _cache
    global _cache_full_warning

    if filename is None:
        cache_home = os.environ.get('XDG_CACHE_HOME') \
            or '%s/.cache' % os.environ['HOME']
        mkdir_p(cache_home + "/stbt")
        filename = cache_home + "/stbt/cache.lmdb"
    with lmdb.open(filename, map_size=MAX_CACHE_SIZE_BYTES) as db:  # pylint: disable=no-member
        assert _cache is None
        try:
            _cache = db
            _cache_full_warning = False
            yield
        finally:
            _cache = None


def memoize(additional_fields=None):
    """
    A decorator to say that the results of a function should be cached.  This is
    used to short circuit expensive image processing functions like OCR.

    A hash is taken of all the decorated functions arguments and any additional
    fields specified to the decorator.  This is used as a key to retrieve a
    previously calculated result from a database on disk.

    **Constraints**

    * The decorated function arguments must be simple JSON serialisable values
      or an image in the form of a numpy.ndarray.
    * The return value from the function must be JSON serialisable and should
      be round-trippable via JSON. This means that unicode objects should be
      returned rather than string objects.
    * For the sake of speed we use a non-cryptographic hash function.  This
      means someone could deliberatly cause a hash-collision by carefully
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

    This function is not a part of the stbt public API and may change without
    warning in future releases.  We hope to stabilise it in the future so users
    can use it with their custom image-processing functions.
    """
    def decorator(function):
        func_key = json.dumps([function.__name__, additional_fields],
                              sort_keys=True)

        @functools.wraps(function)
        def inner(*args, **kwargs):
            try:
                if _cache is None:
                    raise NotCachable()
                full_kwargs = inspect.getcallargs(function, *args, **kwargs)
                key = _cache_hash((func_key, full_kwargs))
                with _cache.begin() as txn:
                    out = txn.get(key)
                if out is not None:
                    return json.loads(out)
                output = function(**full_kwargs)
                with _cache.begin(write=True) as txn:
                    try:
                        txn.put(key, json.dumps(output).encode("utf-8"))
                    except lmdb.MapFullError:  # pylint: disable=no-member
                        global _cache_full_warning
                        if not _cache_full_warning:
                            sys.stderr.write(
                                "Image processing cache is full.  This will "
                                "cause degraded performance.  Consider "
                                "deleting the cache file (%s) to purge old "
                                "results\n" % _cache.path())
                            _cache_full_warning = True
                return output
            except NotCachable:
                return function(*args, **kwargs)

        return inner
    return decorator


class NotCachable(Exception):
    pass


class _ArgsEncoder(json.JSONEncoder):
    def default(self, value):  # pylint: disable=method-hidden
        import _stbt.core as core
        if isinstance(value, ImageLogger):
            if value.enabled:
                raise NotCachable()
            return None
        elif isinstance(value, set):
            return sorted(value)
        elif isinstance(value, core.MatchParameters):
            return {
                "match_method": value.match_method,
                "match_threshold": value.match_threshold,
                "confirm_method": value.confirm_method,
                "confirm_threshold": value.confirm_threshold,
                "erode_passes": value.erode_passes}
        elif isinstance(value, (Gst.Sample, numpy.ndarray)):
            from _stbt.xxhash import Xxhash64
            with numpy_from_sample(value, readonly=True) as s:
                h = Xxhash64()
                h.update(numpy.ascontiguousarray(s).data)
                return (s.shape, h.hexdigest())
        else:
            json.JSONEncoder.default(self, value)


def _cache_hash(value):
    from _stbt.xxhash import Xxhash64
    h = Xxhash64()

    class HashWriter(object):
        def write(self, data):
            h.update(data)
            return len(data)

    json.dump(value, HashWriter(), cls=_ArgsEncoder, sort_keys=True)
    return h.digest()


@contextmanager
def _scoped_curdir():
    with named_temporary_directory() as tmpdir:
        olddir = os.path.abspath(os.curdir)
        os.chdir(tmpdir)
        try:
            yield olddir
        finally:
            os.chdir(olddir)


def test_that_cache_is_disabled_when_debug_match():
    # debug logging is a side effect that the cache cannot reproduce
    import stbt
    import _stbt.logging
    with _scoped_curdir() as srcdir, cache('cache.lmdb'):
        stbt.match(srcdir + '/tests/red-black.png',
                   frame=numpy.zeros((720, 1280, 3), dtype=numpy.uint8))
        assert not os.path.exists('stbt-debug')

        with _stbt.logging.scoped_debug_level(2):
            stbt.match(srcdir + '/tests/red-black.png',
                       frame=numpy.zeros((720, 1280, 3), dtype=numpy.uint8))
        assert os.path.exists('stbt-debug')


def _fields_eq(a, b, fields):
    for x in fields:
        assert type(getattr(a, x)) == type(getattr(b, x))
        if isinstance(getattr(a, x), numpy.ndarray):
            assert (getattr(a, x) == getattr(b, x)).all()
        else:
            assert getattr(a, x) == getattr(b, x)


def _check_cache_behaviour(func):
    from timeit import Timer

    timer = Timer(func)
    uncached_result = func()
    uncached_time = timer.timeit(number=5) / 5.

    with named_temporary_directory() as tmpdir, cache(tmpdir):
        # Prime the cache
        func()
        cached_time = timer.timeit(number=5) / 5.
        cached_result = func()

    print "%s with cache: %s" % (func.__name__, cached_time)
    print "%s without cache: %s" % (func.__name__, uncached_time)

    return cached_time, uncached_time, cached_result, uncached_result


def test_that_cache_speeds_up_match():
    import stbt
    black = numpy.zeros((720, 1280, 3), dtype=numpy.uint8)

    def match():
        return stbt.match('tests/red-black.png', frame=black)

    cached_time, uncached_time, cached_result, uncached_result = (
        _check_cache_behaviour(match))

    assert uncached_time > (cached_time * 4)
    _fields_eq(cached_result, uncached_result,
               ['match', 'region', 'first_pass_result', 'frame', 'image'])


def test_that_cache_speeds_up_ocr():
    import stbt
    import cv2

    frame = cv2.imread('tests/red-black.png')

    def ocr():
        return stbt.ocr(frame=frame)

    cached_time, uncached_time, cached_result, uncached_result = (
        _check_cache_behaviour(ocr))

    assert uncached_time > (cached_time * 10)
    assert type(cached_result) == type(uncached_result)

    assert cached_result == uncached_result


def test_that_cache_speeds_up_match_text():
    import stbt
    import cv2

    frame = cv2.imread('tests/red-black.png')

    def match_text():
        return stbt.match_text("RED", frame=frame)

    cached_time, uncached_time, cached_result, uncached_result = (
        _check_cache_behaviour(match_text))

    assert uncached_time > (cached_time * 10)

    print cached_result

    _fields_eq(cached_result, uncached_result,
               ['match', 'region', 'frame', 'text'])
