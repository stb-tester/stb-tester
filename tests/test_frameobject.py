import threading

import pytest

import stbt_core as stbt


class TruthyFrameObject(stbt.FrameObject):
    """
    The simplest possible FrameObject

    >>> frame = _load_frame("with-dialog")
    >>> bool(TruthyFrameObject(frame))
    True
    >>> TruthyFrameObject(frame)
    <TruthyFrameObject(_frame=<Frame(time=None)>, is_visible=True)>
    """
    @property
    def is_visible(self):
        return True


class FalseyFrameObject(stbt.FrameObject):
    """Properties aren't listed in repr if the FrameObject is falsey.

    >>> frame = _load_frame("with-dialog")
    >>> fo = FalseyFrameObject(frame)
    >>> bool(fo)
    False
    >>> fo
    <FalseyFrameObject(_frame=<Frame(time=None)>, is_visible=False)>
    >>> print(fo.public)
    None
    >>> fo._private
    6
    """
    @property
    def is_visible(self):
        return False

    @property
    def public(self):
        return 5

    @property
    def _private(self):
        return 6


class FrameObjectWithProperties(stbt.FrameObject):
    # pylint:disable=line-too-long
    """Only public properties are listed in repr.

    >>> frame = _load_frame("with-dialog")
    >>> page = FrameObjectWithProperties(frame)
    >>> page
    <FrameObjectWithProperties(_frame=<Frame(time=None)>, is_visible=True, public=...)>
    >>> page.public
    5
    >>> page
    <FrameObjectWithProperties(_frame=<Frame(time=None)>, is_visible=True, public=5)>
    """
    @property
    def is_visible(self):
        return True

    @property
    def public(self):
        return 5

    @property
    def _private(self):
        return 6


class FrameObjectThatCallsItsOwnProperties(stbt.FrameObject):
    # pylint:disable=line-too-long
    """Properties can be called from is_visible.

    >>> frame = _load_frame("with-dialog")
    >>> FrameObjectThatCallsItsOwnProperties(frame)
    <FrameObjectThatCallsItsOwnProperties(_frame=<Frame(time=None)>, is_visible=True, public=5)>
    """
    @property
    def is_visible(self):
        return bool(self.public < self._private)

    @property
    def public(self):
        return 5

    @property
    def _private(self):
        return 6


class PrintingFrameObject(stbt.FrameObject):
    # pylint:disable=line-too-long
    """
    This is a very naughty FrameObject.  It's properties cause side-effects so
    we can check that the caching is working:

    >>> frame = _load_frame("with-dialog")
    >>> m = PrintingFrameObject(frame)
    >>> m.is_visible
    is_visible called
    _helper called
    True
    >>> m.is_visible
    True
    >>> m.another
    another called
    10
    >>> m.another
    10
    >>> m
    <PrintingFrameObject(_frame=<Frame(time=None)>, is_visible=True, another=10)>
    """
    @property
    def is_visible(self):
        print("is_visible called")
        return self._helper

    @property
    def _helper(self):
        print("_helper called")
        return 7

    @property
    def another(self):
        print("another called")
        return self._helper + 3


class FalseyPrintingFrameObject(stbt.FrameObject):
    """Another naughty FrameObject. Properties should be cached even when
    the FrameObject isn't visible.

    >>> frame = _load_frame("with-dialog")
    >>> m = FalseyPrintingFrameObject(frame)
    >>> m.is_visible
    is_visible called
    public called
    _private called
    False
    >>> m.is_visible
    False
    >>> print(m.public)
    None
    >>> print(m.another)
    None
    >>> m._private
    7
    >>> m._another
    _another called
    11
    >>> m._another
    11
    >>> m
    <FalseyPrintingFrameObject(_frame=<Frame(time=None)>, is_visible=False)>
    """
    @property
    def is_visible(self):
        print("is_visible called")
        ten = self.public
        seven = self._private
        return bool(ten < seven)

    @property
    def _private(self):
        print("_private called")
        return 7

    @property
    def public(self):
        print("public called")
        return self._private + 3

    @property
    def another(self):
        print("another called")
        return 10

    @property
    def _another(self):
        print("_another called")
        return 11


def test_that_is_visible_and_properties_arent_racy():
    # Calling a public property on a falsey FrameObject must always return
    # `None`, even if another thread is currently evaluating `is_visible`.
    f = FalseyPrintingFrameObject(_load_frame("with-dialog"))
    results = {}
    threads = []

    def _run(n):
        results[n] = f.public

    for n in range(10):
        t = threading.Thread(target=_run, args=(n,))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()
    print(results)
    assert results == {n: None for n in range(10)}


def _load_frame(name):
    return stbt.Frame(stbt.load_image("images/frameobject/%s.png" % name))


class Dialog(stbt.FrameObject):
    # pylint:disable=line-too-long
    """
    >>> dialog = Dialog(frame=_load_frame('with-dialog'))
    >>> dialog_fab = Dialog(frame=_load_frame('with-dialog2'))
    >>> no_dialog = Dialog(frame=_load_frame('without-dialog'))
    >>> dialog_bunnies = Dialog(_load_frame('with-dialog-different-background'))
    >>> no_dialog_bunnies = Dialog(_load_frame('without-dialog-different-background'))

    Some basic operations:

    >>> print(dialog.message)
    This set-top box is great
    >>> print(dialog_fab.message)
    This set-top box is fabulous

    ``FrameObject`` defines truthiness of your objects based on the mandatory
    ``is_visible`` property:

    >>> bool(dialog)
    True
    >>> bool(no_dialog)
    False

    If ``is_visible`` is falsey, all the rest of the properties will be
    ``None``:

    >>> print(no_dialog.message)
    None

    This enables usage like::

        assert wait_until(lambda: Dialog().title == 'Information')

    ``FrameObject`` defines ``__repr__`` so that you don't have to. It looks
    like this:

    >>> dialog
    <Dialog(_frame=<Frame(time=None)>, is_visible=True, message=u'This set-top box is great', title=...)>
    >>> dialog_fab
    <Dialog(_frame=<Frame(time=None)>, is_visible=True, message=u'This set-top box is fabulous', title=...)>
    >>> no_dialog
    <Dialog(_frame=<Frame(time=None)>, is_visible=False)>

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

    >>> {dialog: 1}
    {<Dialog(_frame=<Frame(time=None)>, is_visible=True, message=u'This set-top box is great', title=u'Information')>: 1}
    >>> len({no_dialog, dialog, dialog, dialog_bunnies})
    2

    Much like ``namedtuple``, ``FrameObject`` classes have a ``_fields``
    attribute.

    >>> Dialog._fields
    ('is_visible', 'message', 'title')

    ``refresh`` returns a new FrameObject of the same type:

    >>> page = Dialog(frame=_load_frame('with-dialog'))
    >>> print(page.message)
    This set-top box is great
    >>> page = page.refresh(_load_frame('with-dialog2'))
    >>> print(page.message)
    This set-top box is fabulous

    """

    @property
    def is_visible(self):
        """
        All Frame Objects must define the ``is_visible`` property, which will
        determine the truthiness of the object. Returning True from this
        property indicates that this Frame Object class can be used with the
        provided frame and that the values of the other properties are likely
        to be valid.

        In this example we only return True if we see the "info" icon that
        appears on each dialog box. The actual work is delegated to the private
        property ``_info`` defined below.

        It's a good idea to return simple types from these properties rather
        than a `MatchResult`, to make the ``__repr__`` cleaner and to preserve
        equality properties.
        """
        return bool(self._info)

    @property
    def title(self):
        """
        The base class provides a ``self._frame`` member. Here we're using
        `stbt.ocr` to extract the dialog's title text from this frame. This is
        the basic form that many Frame Object properties will take.

        This property demonstrates an advantage of Frame Objects. Your
        testcases now look like this::

            assert Dialog().title == "Information"

        instead of this::

            assert stbt.ocr(region=stbt.Region(396, 249, 500, 50)) == "Information"

        This is clearer because it reveals the intention of the testcase author
        (we're looking for the word in the *title* of the dialog). It is also
        easier (cheaper) to maintain: If the position of the title moves, you
        only need to update the implementation of ``Dialog.title``; you won't
        need to change any of your testcases.

        When defining Frame Objects you must take care to pass ``self._frame``
        into every call to an image processing function (like our ``title``
        property does when it calls ``ocr``, above). Otherwise the return
        values won't correspond to the frame you were expecting.
        """
        return stbt.ocr(region=stbt.Region(396, 249, 500, 50),
                        frame=self._frame)

    @property
    def message(self):
        """
        This property demonstrates an advantage of Frame Objects over
        stand-alone helper functions. We are using the position of the "info"
        icon to find this message. Because the private ``_info`` property is
        shared between this property and ``is_visible`` we don't need to
        compute it twice -- the ``FrameObject`` base class will remember the
        value from the first time it was computed.
        """
        right_of_info = stbt.Region(
            x=self._info.region.right, y=self._info.region.y,
            width=390, height=self._info.region.height)
        return stbt.ocr(region=right_of_info, frame=self._frame) \
                   .replace('\n', ' ')

    @property
    def _info(self):
        """
        This is a private property because its name starts with ``_``. It will
        not appear in ``__repr__`` nor count toward equality comparisons, but
        the result from it will still be cached. This is useful for sharing
        intermediate values between your public properties, particularly if
        they are expensive to calculate. In this example we use ``_info`` from
        ``is_visible`` and ``message``.

        You wouldn't want this to be a public property because it returns a
        `MatchResult` which includes the entire frame passed into `match`.
        """
        return stbt.match('tests/info.png', frame=self._frame)


# Tests for "rich comparison" methods ########################################

frame1 = _load_frame("with-dialog")
frame2 = _load_frame("with-dialog2")


class F(stbt.FrameObject):
    def __init__(self, frame, is_visible, a="a", b="b", _c="_c"):
        super().__init__(frame)
        self._is_visible = is_visible
        self._a = a
        self._b = b
        self.__c = _c

    @property
    def is_visible(self):
        return self._is_visible

    @property
    def a(self):
        return self._a

    @property
    def b(self):
        return self._b

    @property
    def _c(self):
        return self.__c


class FF(F):
    pass


class FFF(F):
    @property
    def d(self):
        return "d"


class G(stbt.FrameObject):
    def __init__(self, frame, is_visible, a="a", b="b", _c="_c"):
        super().__init__(frame)
        self._is_visible = is_visible
        self._a = a
        self._b = b
        self.__c = _c

    @property
    def is_visible(self):
        return self._is_visible

    @property
    def a(self):
        return self._a

    @property
    def b(self):
        return self._b

    @property
    def _c(self):
        return self.__c


@pytest.mark.parametrize("f1,f2", [
    # Two instances of the same FrameObject type are considered equal if the
    # values of all the public properties match, even if the underlying frame
    # is different. Private properties don't count.
    (F(frame1, True, a=1, b=2, _c=3), F(frame2, True, a=1, b=2, _c=4)),

    # All falsey FrameObjects of the same type are equal.
    (F(frame1, False, a=1, b=2), F(frame2, False, a=3, b=4)),

    # Subclasses are equal too, as long as they don't have extra properties.
    (F(frame1, True, a=1, b=2), FF(frame2, True, a=1, b=2)),

    # Regression test: `None` properties don't raise TypeError.
    (F(frame1, True, a=1, b=None), F(frame2, True, a=1, b=None)),
])
def test_frameobject_comparison_equal(f1, f2):
    # pylint:disable=comparison-with-itself,unneeded-not
    assert f1 == f1
    assert f1 == f2
    assert f2 == f1
    assert not f1 != f2
    assert not f2 != f1


@pytest.mark.parametrize("f1,f2", [
    # Same type, different property values.
    (F(frame1, True, a=1, b=2), F(frame2, True, a=1, b=3)),
    (F(frame1, True, a=1, b=2), F(frame2, True, a=3, b=2)),
    (F(frame1, True, a=1, b=2), F(frame2, True, a=1, b=None)),

    # Subclass with same properties but different values.
    (F(frame1, True, a=1, b=2), FF(frame2, True, a=1, b=3)),

    # Subclass with additional property.
    (F(frame1, True, a=1, b=2), FFF(frame1, True, a=1, b=2)),

    # Different (unrelated) types.
    (F(frame1, True, a=1, b=2), G(frame2, True, a=1, b=2)),
])
def test_frameobject_comparison_not_equal(f1, f2):
    # pylint:disable=unneeded-not
    assert not f1 == f2
    assert not f2 == f1
    assert f1 != f2
    assert f2 != f1
