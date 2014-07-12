import errno
import os


# User visible exceptions
# ===========================================================================


class UITestError(Exception):
    """The test script had an unrecoverable error."""
    pass


class UITestFailure(Exception):
    """The test failed because the system under test didn't behave as expected.
    """
    pass


# Miscellaneous
# ===========================================================================


def mkdir(d):
    try:
        os.makedirs(d)
    except OSError, e:
        if e.errno != errno.EEXIST:
            return False
    return os.path.isdir(d) and os.access(d, os.R_OK | os.W_OK)
