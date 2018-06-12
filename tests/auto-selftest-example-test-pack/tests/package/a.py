import stbt

from .b import greeting


class GreetingFrameObject(stbt.FrameObject):
    @property
    def is_visible(self):
        return True

    @property
    def greeting(self):
        return greeting()
