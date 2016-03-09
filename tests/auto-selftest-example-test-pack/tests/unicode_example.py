# coding=utf-8
# These are to test the unicode output of `stbt auto-selftest generate`:


def identity(x):
    return x
identity.AUTO_SELFTEST_TRY_SCREENSHOTS = []
identity.AUTO_SELFTEST_SCREENSHOTS = ["frame-object-with-dialog.png"]
identity.AUTO_SELFTEST_EXPRESSIONS = [
    '"Spinal Tap"',
    'u"Spinal Tap"',
    '"Spın̈al Tap"',
    'u"Spın̈al Tap"',
    'print "Spinal Tap"',
    'print u"Spinal Tap"',
    'print "Spın̈al Tap"',
    'print u"Spın̈al Tap"',
    'raise Exception("Spinal Tap")',
    'raise Exception(u"Spinal Tap")',
    'raise Exception("Spın̈al Tap")',
    'raise Exception(u"Spın̈al Tap")',
]


def print_something_unicode(n):
    print [
        "Spinal Tap",
        u"Spinal Tap",
        "Spın̈al Tap",
        u"Spın̈al Tap",
    ][n]
print_something_unicode.AUTO_SELFTEST_TRY_SCREENSHOTS = []
print_something_unicode.AUTO_SELFTEST_SCREENSHOTS = [
    "frame-object-with-dialog.png"]
print_something_unicode.AUTO_SELFTEST_EXPRESSIONS = [
    'print_something_unicode(0)',
    'print_something_unicode(1)',
    'print_something_unicode(2)',
    'print_something_unicode(3)',
]


def return_something_unicode(n):
    return [
        "Spinal Tap",
        u"Spinal Tap",
        "Spın̈al Tap",
        u"Spın̈al Tap",
    ][n]
return_something_unicode.AUTO_SELFTEST_TRY_SCREENSHOTS = []
return_something_unicode.AUTO_SELFTEST_SCREENSHOTS = [
    "frame-object-with-dialog.png"]
return_something_unicode.AUTO_SELFTEST_EXPRESSIONS = [
    'return_something_unicode(0)',
    'return_something_unicode(1)',
    'return_something_unicode(2)',
    'return_something_unicode(3)',
    'print return_something_unicode(0)',
    'print return_something_unicode(1)',
    'print return_something_unicode(2)',
    'print return_something_unicode(3)',
]
