import stbt


# This is a basic frame object that will be run against all our example
# screenshots.  stbt auto-selftest will generate doctests for each of the
# screenshots it matches and not for the screenshots it doesn't.
class Dialog(stbt.FrameObject):
    @property
    def is_visible(self):
        return bool(stbt.match('info.png', frame=self._frame))

    @property
    def message(self):
        return stbt.ocr(region=stbt.Region(515, 331, 400, 100),
                        frame=self._frame).replace('\n', ' ')


# Sometimes we want to force doctests to be written out even if they are falsey.
# This is particularly true if we've added a screenshot that illustrates an
# example that our FrameObject should match but doesn't.  To enforce this we
# set AUTO_SELFTEST_SCREENSHOTS.
class FalseyFrameObject(stbt.FrameObject):
    AUTO_SELFTEST_SCREENSHOTS = ['*-with-*.png']

    @property
    def is_visible(self):
        return False


# If we want an item in a module to be tested we just need to add a
# AUTO_SELFTEST_EXPRESSIONS member to it.  In fact this is exactly why
# stbt auto-selftests knows to test FrameObjects: the FrameObject base class
# defines this member for you.
#
# Here's an example of testing a function instead of a class:
def not_a_frame_object(name, _):
    print "hello %s" % name
    return True

not_a_frame_object.AUTO_SELFTEST_EXPRESSIONS = [
    'not_a_frame_object(4, {frame})',
    'not_a_frame_object(2, {frame})',
]


# And to further illustrate the point here's an example of disabling
# auto-selftests for a FrameObject:
class TruthyFrameObject1(stbt.FrameObject):
    AUTO_SELFTEST_EXPRESSIONS = []

    @property
    def is_visible(self):
        return True


# By default we will try running the Frame Object against every screenshot in
# selftest/screenshots.  We can explicitly set AUTO_SELFTEST_TRY_SCREENSHOTS
# to restrict the screenshots it's checked against.  This defaults to ['*.png']:
class TruthyFrameObject2(stbt.FrameObject):
    AUTO_SELFTEST_TRY_SCREENSHOTS = ['*-without-*.png']

    @property
    def is_visible(self):
        return True
