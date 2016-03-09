# There should be no selftest file generated for this file because there are
# no tests to be generated.

import stbt


class NoTestFrameObject(stbt.FrameObject):
    AUTO_SELFTEST_EXPRESSIONS = []

    @property
    def is_visible(self):
        return True


class NoScreenshotFrameObject(stbt.FrameObject):
    AUTO_SELFTEST_TRY_SCREENSHOTS = []

    @property
    def is_visible(self):
        return True
