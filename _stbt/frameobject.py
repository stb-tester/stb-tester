"""
Copyright 2016-2018 Stb-tester.com Ltd.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).
"""
import functools
import threading


def _memoize_property_fn(fn):
    @functools.wraps(fn)
    def inner(self):
        # pylint: disable=protected-access
        if fn not in self._FrameObject__frame_object_cache:
            self._FrameObject__frame_object_cache[fn] = fn(self)
        return self._FrameObject__frame_object_cache[fn]
    return inner


def _mark_in_is_visible(fn):
    @functools.wraps(fn)
    def inner(self):
        # pylint: disable=protected-access
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
        # pylint: disable=protected-access
        if (getattr(self._FrameObject__local, "in_is_visible", 0) or
                self.is_visible):
            return fn(self)
        else:
            return None
    return inner


class _FrameObjectMeta(type):
    def __new__(mcs, name, parents, dct):
        for k, v in dct.iteritems():
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

        if 'AUTO_SELFTEST_EXPRESSIONS' not in dct:
            dct['AUTO_SELFTEST_EXPRESSIONS'] = ['%s(frame={frame})' % name]

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


class FrameObject(object):
    # pylint: disable=line-too-long
    r'''Base class for user-defined Frame Objects.

    The Frame Object pattern is used to simplify testcase development and
    maintenance. Frame Objects are a layer of abstraction between your
    testcases and the stbt image processing APIs. They are easy to write and
    cheap to maintain.

    A Frame Object extracts information from a frame of video, typically by
    calling `stbt.ocr` or `stbt.match`. All of your testcases use these objects
    rather than using `ocr` or `match` directly. A Frame Object translates from
    the vocabulary of low-level image processing functions and regions (like
    ``stbt.ocr(region=stbt.Region(213, 23, 200, 36))``) to the vocabulary of
    high-level features and user-facing concepts (like ``programme_title``).

    ``FrameObject`` is a base class that makes it easier to create well-behaved
    Frame Objects. Your own Frame Object classes should:

    1. Derive from ``FrameObject``.
    2. Define an ``is_visible`` property that returns True or False.
    3. Define any other properties for information that you want to extract
       from the frame.
    4. Take care to pass ``self._frame`` into any image processing function you
       call.

    A Frame Object instance is considered "truthy" if it is visible. Any other
    properties (apart from ``is_visible``) will return ``None`` if the object
    isn't visible.

    Frame Objects are immutable, because they represent information about a
    specific frame of video. If you define any methods that change the state of
    the device-under-test, they should return a new Frame Object instead of
    modifying ``self``.

    Each property will be cached the first time is is referenced. This allows
    writing test cases in a natural way while expensive operations like ``ocr``
    will only be done once per frame.

    The ``FrameObject`` base class defines the following methods:

    * ``__init__`` -- The default constructor takes an optional frame; if the
      frame is not provided, it will grab a frame from the device-under-test.
    * ``__nonzero__`` -- Delegates to ``is_visible``. The object will only be
      considered True if it is visible.
    * ``__repr__`` -- The object's string representation includes all the
      user-defined public properties.
    * ``__hash__`` and ``__cmp__`` -- Two instances of the same ``FrameObject``
      type are considered equal if the values of all the public properties
      match, even if the underlying frame is different.

    For more background information on Frame Objects see
    `Improve black-box testing agility: meet the Frame Object pattern
    <https://stb-tester.com/blog/2015/09/08/meet-the-frame-object-pattern>`__.

    **Example**

    We'll create a Frame Object class for the dialog box we see in this image
    that we've captured from our (hypothetical) set-top box:

    .. figure:: images/frame-object-with-dialog.png
       :alt: screenshot of dialog box

    Here's our Frame Object class:

    >>> import stbt
    >>> class Dialog(stbt.FrameObject):
    ...     @property
    ...     def is_visible(self):
    ...         return bool(self._info)
    ...
    ...     @property
    ...     def title(self):
    ...         return stbt.ocr(region=stbt.Region(396, 249, 500, 50),
    ...                         frame=self._frame)
    ...
    ...     @property
    ...     def message(self):
    ...         right_of_info = stbt.Region(
    ...             x=self._info.region.right, y=self._info.region.y,
    ...             width=390, height=self._info.region.height)
    ...         return stbt.ocr(region=right_of_info, frame=self._frame) \
    ...                .replace('\n', ' ')
    ...
    ...     @property
    ...     def _info(self):
    ...         return stbt.match('tests/info.png', frame=self._frame)

    Let's take this line by line::

        class Dialog(FrameObject):

    We create a class deriving from the ``FrameObject`` base class.

    ::

        @property
        def is_visible(self):
            return bool(self._info)

    All Frame Objects must define the ``is_visible`` property, which will
    determine the truthiness of the object. Returning True from this property
    indicates that this Frame Object class can be used with the provided frame
    and that the values of the other properties are likely to be valid.

    In this example we only return True if we see the "info" icon that appears
    on each dialog box. The actual work is delegated to the private property
    ``_info`` defined below.

    It's a good idea to return simple types from these properties rather than a
    `MatchResult`, to make the ``__repr__`` cleaner and to preserve equality
    properties.

    ::

        @property
        def title(self):
            return ocr(region=Region(396, 249, 500, 50), frame=self._frame)

    The base class provides a ``self._frame`` member. Here we're using
    `stbt.ocr` to extract the dialog's title text from this frame. This is the
    basic form that many Frame Object properties will take.

    This property demonstrates an advantage of Frame Objects. Your testcases
    now look like this::

        assert Dialog().title == "Information"

    instead of this::

        assert stbt.ocr(region=stbt.Region(396, 249, 500, 50)) == "Information"

    This is clearer because it reveals the intention of the testcase author
    (we're looking for the word in the *title* of the dialog). It is also
    easier (cheaper) to maintain: If the position of the title moves, you only
    need to update the implementation of ``Dialog.title``; you won't need to
    change any of your testcases.

    When defining Frame Objects you must take care to pass ``self._frame`` into
    every call to an image processing function (like our ``title`` property
    does when it calls ``ocr``, above). Otherwise the return values won't
    correspond to the frame you were expecting.

    ::

        @property
        def message(self):
            right_of_info = Region(
                x=self._info.region.right, y=self._info.region.y,
                width=390, height=self._info.region.height)
            return ocr(region=right_of_info, frame=self._frame) \
                   .replace('\n', ' ')

    This property demonstrates an advantage of Frame Objects over stand-alone
    helper functions. We are using the position of the "info" icon to find this
    message. Because the private ``_info`` property is shared between this
    property and ``is_visible`` we don't need to compute it twice -- the
    ``FrameObject`` base class will remember the value from the first time it
    was computed.

    ::

        @property
        def _info(self):
            return match('../tests/info.png', frame=self._frame)

    This is a private property because its name starts with ``_``. It will not
    appear in ``__repr__`` nor count toward equality comparisons, but the
    result from it will still be cached. This is useful for sharing
    intermediate values between your public properties, particularly if they
    are expensive to calculate. In this example we use ``_info`` from
    ``is_visible`` and ``message``.

    You wouldn't want this to be a public property because it returns a
    `MatchResult` which includes the entire frame passed into `match`.

    **Using our new Frame Object class**

    The default constructor will grab a frame from the device-under-test. This
    allows you to use Frame Objects with `wait_until` like this::

        dialog = wait_until(Dialog)
        assert 'great' in dialog.message

    We can also explicitly pass in a frame. This is mainly useful for
    unit-testing your Frame Objects.

    The examples below will use these example frames:

    .. testsetup::

        >>> from tests.test_frame_object import _load_frame
        >>> dialog = Dialog(frame=_load_frame('with-dialog'))
        >>> dialog_fab = Dialog(frame=_load_frame('with-dialog2'))
        >>> no_dialog = Dialog(frame=_load_frame('without-dialog'))
        >>> dialog_bunnies = Dialog(_load_frame('with-dialog-different-background'))
        >>> no_dialog_bunnies = Dialog(_load_frame('without-dialog-different-background'))

    .. |dialog| image:: images/frame-object-with-dialog.png
    .. |dialog_fab| image:: images/frame-object-with-dialog2.png
    .. |no_dialog| image:: images/frame-object-without-dialog.png
    .. |dialog_bunnies| image:: images/frame-object-with-dialog-different-background.png
    .. |no_dialog_bunnies| image:: images/frame-object-without-dialog-different-background.png

    +---------------------+---------------------+
    | dialog              | no_dialog           |
    |                     |                     |
    | |dialog|            | |no_dialog|         |
    +---------------------+---------------------+
    | dialog_bunnies      | no_dialog_bunnies   |
    |                     |                     |
    | |dialog_bunnies|    | |no_dialog_bunnies| |
    +---------------------+---------------------+
    | dialog_fab          |                     |
    |                     |                     |
    | |dialog_fab|        |                     |
    +---------------------+---------------------+

    Some basic operations:

    >>> print dialog.message
    This set-top box is great
    >>> print dialog_fab.message
    This set-top box is fabulous

    ``FrameObject`` defines truthiness of your objects based on the mandatory
    ``is_visible`` property:

    >>> bool(dialog)
    True
    >>> bool(no_dialog)
    False

    If ``is_visible`` is falsey, all the rest of the properties will be
    ``None``:

    >>> print no_dialog.message
    None

    This enables usage like::

        assert wait_until(lambda: Dialog().title == 'Information')

    ``FrameObject`` defines ``__repr__`` so that you don't have to. It looks
    like this:

    >>> dialog
    Dialog(is_visible=True, message=u'This set-top box is great', title=u'Information')
    >>> dialog_fab
    Dialog(is_visible=True, message=u'This set-top box is fabulous', title=u'Information')
    >>> no_dialog
    Dialog(is_visible=False)

    This makes it convenient to use doctests for unit-testing your Frame
    Objects.

    Frame Objects with identical property values are equal, even if the backing
    frames are not:

    >>> assert dialog == dialog
    >>> assert dialog == dialog_bunnies
    >>> assert dialog != dialog_fab
    >>> assert dialog != no_dialog

    This can be useful for detecting changes in the UI (while ignoring live TV
    in the background) or waiting for the UI to stop changing before
    interrogating it.

    All falsey Frame Objects of the same type are equal:

    >>> assert no_dialog == no_dialog
    >>> assert no_dialog == no_dialog_bunnies

    ``FrameObject`` defines ``__hash__`` too so you can store them in a set or
    in a dict:

    >>> {dialog}
    set([Dialog(is_visible=True, message=u'This set-top box is great', title=u'Information')])
    >>> len({no_dialog, dialog, dialog, dialog_bunnies})
    2

    Much like ``namedtuple``, ``FrameObject`` classes have a ``_fields``
    attribute.

    >>> Dialog._fields
    ('is_visible', 'message', 'title')

    Added in v30: The ``_fields`` attribute.
    '''
    __metaclass__ = _FrameObjectMeta

    def __init__(self, frame=None):
        if frame is None:
            import stbt
            frame = stbt.get_frame()
        self.__frame_object_cache = {}
        self.__local = threading.local()
        self._frame = frame

    def __repr__(self):
        args = ", ".join(("%s=%r" % x) for x in self._iter_fields())
        return "%s(%s)" % (self.__class__.__name__, args)

    def _iter_fields(self):
        if self:
            for x in self._fields:  # pylint:disable=no-member
                yield x, getattr(self, x)
        else:
            yield "is_visible", False

    def __nonzero__(self):
        return bool(self.is_visible)

    def __cmp__(self, other):
        # pylint: disable=protected-access
        from itertools import izip_longest
        if isinstance(other, self.__class__):
            for s, o in izip_longest(self._iter_fields(), other._iter_fields()):
                v = cmp(s[1], o[1])
                if v != 0:
                    return v
            return 0
        else:
            return NotImplemented

    def __hash__(self):
        return hash(tuple(v for _, v in self._iter_fields()))

    @property
    def is_visible(self):
        raise NotImplementedError(
            "Objects deriving from FrameObject must define an is_visible "
            "property")
