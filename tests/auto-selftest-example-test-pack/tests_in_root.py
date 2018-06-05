import stbt


# This is a basic frame object that will be run against all our example
# screenshots.  stbt auto-selftest will generate doctests for each of the
# screenshots it matches and not for the screenshots it doesn't.
class Dialog(stbt.FrameObject):
    @property
    def is_visible(self):
        return bool(stbt.match('tests/info.png', frame=self._frame))

    @property
    def message(self):
        return stbt.ocr(region=stbt.Region(515, 331, 400, 100),
                        frame=self._frame).replace('\n', ' ')
