"""
Copyright 2016-2018 Stb-tester.com Ltd.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).
"""

import functools
import threading

try:
    from itertools import zip_longest
except ImportError:
    # Python 2:
    from itertools import izip_longest as zip_longest


def for_object_repository(cls=None):
    """A decorator that marks classes and functions so they appear in the Object
    Repository.

    Classes that directly derive from `stbt.FrameObject` have this decorator
    applied to them automatically.  This can be used to register other classes
    and functions.

    Usage:

        @for_object_repository
        class MyClass():
            ...
    """
    # These classes are extracted by static analysis, so return the class
    # unchanged:
    if cls is None:
        # Called like:
        #
        #     @for_object_repository()
        #     class MyClass():
        def decorator(cls):
            return cls
        return decorator
    else:
        # Called like:
        #
        #    @for_object_repository
        #    class MyClass():
        return cls


def _memoize_property_fn(fn):
    @functools.wraps(fn)
    def inner(self):
        if fn not in self._FrameObject__frame_object_cache:
            self._FrameObject__frame_object_cache[fn] = fn(self)
        return self._FrameObject__frame_object_cache[fn]
    return inner


def _mark_in_is_visible(fn):
    @functools.wraps(fn)
    def inner(self):
        try:
            self._FrameObject__local.in_is_visible += 1
        except AttributeError:
            self._FrameObject__local.in_is_visible = 1
        try:
            return bool(fn(self))
        finally:
            self._FrameObject__local.in_is_visible -= 1
    return inner


def _noneify_property_fn(fn):
    @functools.wraps(fn)
    def inner(self):
        if (getattr(self._FrameObject__local, "in_is_visible", 0) or
                self.is_visible):
            return fn(self)
        else:
            return None
    return inner


class _FrameObjectMeta(type):
    def __new__(mcs, name, parents, dct):
        for k, v in dct.items():
            if isinstance(v, property):
                # Properties must not have setters
                if v.fset is not None:
                    raise Exception(
                        "FrameObjects must be immutable but this property has "
                        "a setter")
                f = v.fget
                # The value of any property is cached after the first use
                f = _memoize_property_fn(f)
                # Public properties return `None` if the FrameObject isn't
                # visible.
                if k == 'is_visible':
                    f = _mark_in_is_visible(f)
                elif not k.startswith('_'):
                    f = _noneify_property_fn(f)
                dct[k] = property(f)

        return super(_FrameObjectMeta, mcs).__new__(mcs, name, parents, dct)

    def __init__(cls, name, parents, dct):
        property_names = sorted([
            p for p in dir(cls)
            if isinstance(getattr(cls, p), property)])
        assert 'is_visible' in property_names
        cls._fields = tuple(["is_visible"] + sorted(
            x for x in property_names
            if x != "is_visible" and not x.startswith('_')))
        super(_FrameObjectMeta, cls).__init__(name, parents, dct)


class FrameObject(metaclass=_FrameObjectMeta):
    r'''Base class for user-defined Page Objects.

    FrameObjects are Stb-tester's implementation of the *Page Object* pattern.
    A FrameObject is a class that uses Stb-tester APIs like ``stbt.match()``
    and ``stbt.ocr()`` to extract information from the screen, and it provides
    a higher-level API in the vocabulary and user-facing concepts of your own
    application.

    .. figure:: images/object-repository/frame-object-pattern.png
       :align: center

       Based on Martin Fowler's `PageObject <fowler_>`_ diagram

    Stb-tester uses a separate instance of your FrameObject class for each
    frame of video captured from the device-under-test (hence the name "Frame
    Object"). Stb-tester provides additional tooling for writing, testing,
    and maintenance of FrameObjects.

    To define your own FrameObject class:

    * Derive from ``stbt.FrameObject``.
    * Define an ``is_visible`` property (using Python's `@property`_ decorator)
      that returns True or False.
    * Define any other properties for information that you want to extract
      from the frame.
    * Inside each property, when you call an image-processing function (like
      `stbt.match` or `stbt.ocr`) you must specify the parameter
      ``frame=self._frame``.

    The following behaviours are provided automatically by the FrameObject
    base class:

    * **Truthiness:** A FrameObject instance is considered "truthy" if it is
      visible. Any other properties (apart from ``is_visible``) will return
      ``None`` if the object isn't visible.

    * **Immutability:** FrameObjects are immutable, because they represent
      information about a specific frame of video -- in other words, an
      instance of a FrameOject represents the state of the device-under-test at
      a specific point in time. If you define any methods that change the state
      of the device-under-test, they should return a new FrameObject instance
      instead of modifying ``self``.

    * **Caching:** Each property will be cached the first time is is used. This
      allows writing testcases in a natural way, while expensive operations
      like ``ocr`` will only be done once per frame.

    The FrameObject base class defines several convenient methods and
    attributes (see below).

    For more details see `Object Repository`_ in the Stb-tester manual.

    .. _@property: https://docs.python.org/3.6/library/functions.html#property
    .. _fowler: https://martinfowler.com/bliki/PageObject.html
    .. _Object Repository: https://stb-tester.com/manual/object-repository

    Added in v30: ``_fields`` and ``refresh``.
    '''

    def __init__(self, frame=None):
        """The default constructor takes an optional frame of video; if the
        frame is not provided, it will grab a frame from the device-under-test.

        If you override the constructor in your derived class (for example to
        accept additional parameters), make sure to accept an optional
        ``frame`` parameter and supply it to the super-class's constructor.
        """
        if frame is None:
            from stbt_core import get_frame
            frame = get_frame()
        self.__frame_object_cache = {}
        self.__local = threading.local()
        self._frame = frame

    def __repr__(self):
        """
        The object's string representation includes all its public properties.
        """
        args = ", ".join(("%s=%r" % x) for x in self._iter_fields())
        return "%s(%s)" % (self.__class__.__name__, args)

    def _iter_fields(self):
        if self:
            for x in self._fields:  # pylint:disable=no-member
                yield x, getattr(self, x)
        else:
            yield "is_visible", False

    def __bool__(self):
        """
        Delegates to ``is_visible``. The object will only be considered True if
        it is visible.
        """
        return bool(self.is_visible)

    def __eq__(self, other):
        """
        Two instances of the same ``FrameObject`` type are considered equal if
        the values of all the public properties match, even if the underlying
        frame is different. All falsey FrameObjects of the same type are equal.
        """
        if isinstance(other, self.__class__):
            for s, o in zip_longest(self._iter_fields(), other._iter_fields()):
                if s != o:
                    return False
            return True
        else:
            return NotImplemented

    def __hash__(self):
        """
        Two instances of the same ``FrameObject`` type are considered equal if
        the values of all the public properties match, even if the underlying
        frame is different. All falsey FrameObjects of the same type are equal.
        """
        return hash(tuple(v for _, v in self._iter_fields()))

    @property
    def is_visible(self):
        raise NotImplementedError(
            "Objects deriving from FrameObject must define an is_visible "
            "property")

    def refresh(self, frame=None, **kwargs):
        """
        Returns a new FrameObject instance with a new frame. ``self`` is not
        modified.

        ``refresh`` is used by navigation functions that modify the state of
        the device-under-test.

        By default ``refresh`` returns a new object of the same class as
        ``self``, but you can override the return type by implementing
        ``refresh`` in your derived class.

        Any additional keyword arguments are passed on to ``__init__``.
        """
        return type(self)(frame=frame, **kwargs)
