import errno
import os
import tempfile
from contextlib import contextmanager
from shutil import rmtree


def mkdir_p(d):
    """Python 3.2 has an optional argument to os.makedirs called exist_ok.  To
    support older versions of python we can't use this and need to catch
    exceptions"""
    try:
        os.makedirs(d)
    except OSError, e:
        if e.errno == errno.EEXIST and os.path.isdir(d) \
                and os.access(d, os.R_OK | os.W_OK):
            return
        else:
            raise


@contextmanager
def named_temporary_directory(
        suffix='', prefix='tmp', dir=None):  # pylint: disable=W0622
    dirname = tempfile.mkdtemp(suffix, prefix, dir)
    try:
        yield dirname
    finally:
        rmtree(dirname)


def safe_unicode(obj):
    try:
        return unicode(obj)
    except UnicodeDecodeError:
        # e.g. byte string with UTF-8 bytes.
        s = str(obj).decode('utf-8', 'backslashreplace')
        return unicode(s)
