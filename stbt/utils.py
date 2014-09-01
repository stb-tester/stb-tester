import errno
import os
import tempfile
from contextlib import contextmanager
from shutil import rmtree


def mkdir(d):
    try:
        os.makedirs(d)
    except OSError, e:
        if e.errno != errno.EEXIST:
            return False
    return os.path.isdir(d) and os.access(d, os.R_OK | os.W_OK)


@contextmanager
def named_temporary_directory(
        suffix='', prefix='tmp', dir=None):  # pylint: disable=W0622
    dirname = tempfile.mkdtemp(suffix, prefix, dir)
    try:
        yield dirname
    finally:
        rmtree(dirname)
