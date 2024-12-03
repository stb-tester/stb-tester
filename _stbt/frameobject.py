"""
Copyright 2016-2018 Stb-tester.com Ltd.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).
"""

from __future__ import annotations

import functools
import threading
from itertools import zip_longest
from typing import Callable, Optional, overload, TypeVar

from .imgutils import FrameT


T = TypeVar("T")


@overload
def for_object_repository(cls: T) -> T:
    ...


@overload
def for_object_repository() -> Callable[[T], T]:
    ...


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
        if fn.__name__ not in self._FrameObject__frame_object_cache:
            self._FrameObject__frame_object_cache[fn.__name__] = fn(self)
        return self._FrameObject__frame_object_cache[fn.__name__]
    return inner


def _convert_is_visible_to_bool(fn):
    @functools.wraps(fn)
    def inner(self):
        return bool(fn(self))
    return inner


def _mark_in_is_visible(fn):
    @functools.wraps(fn)
    def inner(self):
        try:
            self._FrameObject__local.in_is_visible += 1
        except AttributeError:
            self._FrameObject__local.in_is_visible = 1
        try:
            return fn(self)
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
                    raise TypeError(
                        f"FrameObjects must be immutable but property {k!r} "
                        "has a setter")
                f = v.fget
                if k == 'is_visible':
                    f = _convert_is_visible_to_bool(f)
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

    For more details see `Object Repository`_ in the Stb-tester manual.

    The FrameObject base class defines several convenient methods and
    attributes:

    .. _@property: https://docs.python.org/3.6/library/functions.html#property
    .. _fowler: https://martinfowler.com/bliki/PageObject.html
    .. _Object Repository: https://stb-tester.com/manual/object-repository
    '''

    def __init__(self, frame: Optional[FrameT] = None) -> None:
        """The default constructor takes an optional frame of video; if the
        frame is not provided, it will grab a live frame from the
        device-under-test.

        If you override the constructor in your derived class (for example to
        accept additional parameters), make sure to accept an optional
        ``frame`` parameter and supply it to the super-class's constructor.
        """
        if frame is None:
            from stbt_core import get_frame
            frame = get_frame()
        self.__frame_object_cache = {}  # pylint:disable=unused-private-member
        self.__local = threading.local()  # pylint:disable=unused-private-member
        self._frame = frame

    def __repr__(self) -> str:
        """The object's string representation shows all its public properties.

        We only print properties we have already calculated, to avoid
        triggering expensive calculations.
        """
        if self:
            args = []
            for x in self._fields:  # pylint:disable=no-member
                name = getattr(self.__class__, x).fget.__name__
                if name in self.__frame_object_cache:
                    args.append("%s=%r" % (
                        name, self.__frame_object_cache[name]))
                else:
                    args.append("%s=..." % (name,))
        else:
            args = ["is_visible=False"]
        return "<%s(_frame=%r, %s)>" % (self.__class__.__name__,
                                        self._frame,
                                        ", ".join(args))

    def _iter_fields(self):
        if self:
            for x in self._fields:  # pylint:disable=no-member
                yield x, getattr(self, x)
        else:
            yield "is_visible", False

    def __bool__(self) -> bool:
        """
        Delegates to ``is_visible``. The object will only be considered True if
        it is visible.
        """
        return bool(self.is_visible)

    def __eq__(self, other) -> bool:
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

    def __hash__(self) -> int:
        """
        Two instances of the same ``FrameObject`` type are considered equal if
        the values of all the public properties match, even if the underlying
        frame is different. All falsey FrameObjects of the same type are equal.
        """
        return hash(tuple(v for _, v in self._iter_fields()))

    @property
    def is_visible(self) -> bool:
        raise NotImplementedError(
            "Objects deriving from FrameObject must define an is_visible "
            "property")

    def refresh(self: T, frame: Optional[FrameT] = None, **kwargs) -> T:
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
        return self.__class__(frame=frame, **kwargs)  # type:ignore
