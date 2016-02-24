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


def _load_frame(name):
    import cv2
    from os.path import abspath, dirname
    filename = "%s/frame-object-%s.png" % (dirname(abspath(__file__)), name)
    frame = cv2.imread(filename)
    if frame is None:
        raise ValueError("Couldn't load test image %r" % filename)
    return frame
