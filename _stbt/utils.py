import errno
import os
import sys
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


def import_by_filename(filename_):
    module_dir, module_file = os.path.split(filename_)
    module_name, module_ext = os.path.splitext(module_file)
    if module_ext != '.py':
        raise ImportError("Invalid module filename '%s'" % filename_)
    sys.path = [os.path.abspath(module_dir)] + sys.path
    return __import__(module_name)


def parse_test_uri(test_uri):
    """Deconstruct a given `test_uri` into its component parts.

    Returns (<str> abspath, <str> function name, <callable> function).

    If `test_uri` is simply a filepath then the return is
    (abspath(`test_uri`), "", None)
    """
    if '::' in test_uri:
        filename, funcname = test_uri.split('::', 1)
        absfilename = os.path.abspath(filename)
        module = import_by_filename(filename)
        function = getattr(module, funcname)
    else:
        absfilename = os.path.abspath(test_uri)
        funcname, function = "", None
    return absfilename, funcname, function
