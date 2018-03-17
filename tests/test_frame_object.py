import threading

import stbt


class TruthyFrameObject(stbt.FrameObject):
    """
    The simplest possible FrameObject

    >>> frame = _load_frame("with-dialog")
    >>> bool(TruthyFrameObject(frame))
    True
    >>> TruthyFrameObject(frame)
    TruthyFrameObject(is_visible=True)
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
    FalseyFrameObject(is_visible=False)
    >>> print fo.public
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
    """Only public properties are listed in repr.

    >>> frame = _load_frame("with-dialog")
    >>> FrameObjectWithProperties(frame)
    FrameObjectWithProperties(is_visible=True, public=5)
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
    """Properties can be called from is_visible.

    >>> frame = _load_frame("with-dialog")
    >>> FrameObjectThatCallsItsOwnProperties(frame)
    FrameObjectThatCallsItsOwnProperties(is_visible=True, public=5)
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


class OrderedFrameObject(stbt.FrameObject):
    """
    FrameObject defines a default sort order based on the values of the
    public properties (in lexicographical order by property name; that is, in
    this example the `color` value is compared before `size`):

    >>> import numpy
    >>> red = OrderedFrameObject(numpy.array([[[0, 0, 255]]]))
    >>> bigred = OrderedFrameObject(numpy.array([[[0, 0, 255], [0, 0, 255]]]))
    >>> green = OrderedFrameObject(numpy.array([[[0, 255, 0]]]))
    >>> blue = OrderedFrameObject(numpy.array([[[255, 0, 0]]]))
    >>> print sorted([red, green, blue, bigred])
    [...'blue'..., ...'green'..., ...'red', size=1..., ...'red', size=2)]
    """

    @property
    def is_visible(self):
        return True

    @property
    def size(self):
        return self._frame.shape[0] * self._frame.shape[1]

    @property
    def color(self):
        if self._frame[0, 0, 0] == 255:
            return "blue"
        elif self._frame[0, 0, 1] == 255:
            return "green"
        elif self._frame[0, 0, 2] == 255:
            return "red"
        else:
            return "grey?"


class PrintingFrameObject(stbt.FrameObject):
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
    PrintingFrameObject(is_visible=True, another=10)
    """
    @property
    def is_visible(self):
        print "is_visible called"
        return self._helper

    @property
    def _helper(self):
        print "_helper called"
        return 7

    @property
    def another(self):
        print "another called"
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
    >>> print m.public
    None
    >>> print m.another
    None
    >>> m._private
    7
    >>> m._another
    _another called
    11
    >>> m._another
    11
    >>> m
    FalseyPrintingFrameObject(is_visible=False)
    """
    @property
    def is_visible(self):
        print "is_visible called"
        ten = self.public
        seven = self._private
        return bool(ten < seven)

    @property
    def _private(self):
        print "_private called"
        return 7

    @property
    def public(self):
        print "public called"
        return self._private + 3

    @property
    def another(self):
        print "another called"
        return 10

    @property
    def _another(self):
        print "_another called"
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
    print results
    assert results == {n: None for n in range(10)}


def _load_frame(name):
    import cv2
    from os.path import abspath, dirname
    filename = "%s/%s/frame-object-%s.png" % (
        dirname(abspath(__file__)),
        "auto-selftest-example-test-pack/selftest/screenshots",
        name)
    frame = cv2.imread(filename)
    if frame is None:
        raise ValueError("Couldn't load test image %r" % filename)
    return frame
