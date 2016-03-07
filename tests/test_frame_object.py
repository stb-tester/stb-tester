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
        return bool(self._helper)

    @property
    def _helper(self):
        print "_helper called"
        return 7

    @property
    def another(self):
        print "another called"
        return self._helper + 3


def _load_frame(name):
    import cv2
    from os.path import abspath, dirname
    filename = "%s/frame-object-%s.png" % (dirname(abspath(__file__)), name)
    frame = cv2.imread(filename)
    if frame is None:
        raise ValueError("Couldn't load test image %r" % filename)
    return frame
