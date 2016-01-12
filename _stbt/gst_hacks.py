import ctypes
import platform
from contextlib import contextmanager
from os.path import dirname

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst  # isort:skip pylint: disable=E0611

# Here we are using ctypes to call `gst_buffer_map` and `gst_buffer_unmap`
# because PyGObject does not properly expose struct GstMapInfo (see
# [bz #678663]).  Apparently this is fixed upstream but we are still awaiting
# an upstream release (Mar 2014).  Hopefully this can be removed in the future.

_GST_PADDING = 4  # From gstconfig.h


# From struct GstMapInfo in gstreamer/gst/gstmemory.h:
class _GstMapInfo(ctypes.Structure):
    _fields_ = [("memory", ctypes.c_void_p),   # GstMemory *memory
                ("flags", ctypes.c_int),       # GstMapFlags flags
                ("data", ctypes.POINTER(ctypes.c_byte)),    # guint8 *data
                ("size", ctypes.c_size_t),     # gsize size
                ("maxsize", ctypes.c_size_t),  # gsize maxsize
                ("user_data", ctypes.c_void_p * 4),     # gpointer user_data[4]
                # gpointer _gst_reserved[GST_PADDING]:
                ("_gst_reserved", ctypes.c_void_p * _GST_PADDING)]

_GstMapInfo_p = ctypes.POINTER(_GstMapInfo)

if platform.system() == "Darwin":
    _libgst = ctypes.CDLL(dirname(Gst.__path__) + "/../libgstreamer-1.0.dylib")
else:
    _libgst = ctypes.CDLL("libgstreamer-1.0.so.0")
_libgst.gst_buffer_map.argtypes = [ctypes.c_void_p, _GstMapInfo_p, ctypes.c_int]
_libgst.gst_buffer_map.restype = ctypes.c_int

_libgst.gst_buffer_unmap.argtypes = [ctypes.c_void_p, _GstMapInfo_p]
_libgst.gst_buffer_unmap.restype = None

_libgst.gst_sample_get_buffer.argtypes = [ctypes.c_void_p]
_libgst.gst_sample_get_buffer.restype = ctypes.c_void_p

_libgst.gst_mini_object_is_writable.argtypes = [ctypes.c_void_p]
_libgst.gst_mini_object_is_writable.restype = ctypes.c_int


@contextmanager
def _map_gst_buffer(pbuffer, flags):
    if pbuffer is None:
        raise TypeError("Cannot pass NULL to _map_gst_buffer")
    if flags & Gst.MapFlags.WRITE \
            and _libgst.gst_mini_object_is_writable(pbuffer) == 0:
        raise ValueError(
            "Writable array requested but buffer is not writeable")

    mapping = _GstMapInfo()
    success = _libgst.gst_buffer_map(pbuffer, mapping, flags)
    if not success:
        raise RuntimeError("Couldn't map buffer")
    try:
        yield ctypes.cast(
            mapping.data, ctypes.POINTER(ctypes.c_byte * mapping.size)).contents
    finally:
        _libgst.gst_buffer_unmap(pbuffer, mapping)


def map_gst_sample(sample, flags):
    """
    This function exists because of a change in behaviour of pygobject 3.13 that
    broke our ability to get a writable buffer from a GstSample.

    See https://bugzilla.gnome.org/show_bug.cgi?id=736896 for more information.
    """
    if not isinstance(sample, Gst.Sample):
        raise TypeError("map_gst_sample must take a Gst.Sample.  Received a %s"
                        % str(type(sample)))

    # hashing a GObject actually gives the address (pointer) of the C struct
    # that backs it!:
    pbuffer = _libgst.gst_sample_get_buffer(hash(sample))
    if pbuffer is None:
        raise ValueError(
            "map_gst_sample: Provided GstSample doesn't contain a buffer")

    return _map_gst_buffer(pbuffer, flags)


def test_map_sample_reading_data():
    Gst.init([])

    s = Gst.Sample.new(Gst.Buffer.new_wrapped("hello"), None, None, None)
    with map_gst_sample(s, Gst.MapFlags.READ) as a:
        assert 'hello' == ''.join(chr(x) for x in a)


def test_map_sample_modifying_data():
    Gst.init([])

    s = Gst.Sample.new(Gst.Buffer.new_wrapped("hello"), None, None, None)
    with map_gst_sample(s, Gst.MapFlags.WRITE | Gst.MapFlags.READ) as a:
        a[2] = 1

    assert s.get_buffer().extract_dup(0, 5) == "he\x01lo"


def test_map_sample_without_buffer():
    Gst.init([])

    sample = Gst.Sample.new(None, None, None, None)
    try:
        # pylint: disable=E1120
        with map_gst_sample(sample, Gst.MapFlags.READ):
            assert False
    except ValueError:
        pass


def gst_iterate(gst_iterator):
    """Wrap a Gst.Iterator to expose the Python iteration protocol.  The
    gst-python package exposes similar functionality on Gst.Iterator itself so
    this code should be retired in the future once gst-python is broadly enough
    available."""
    result = Gst.IteratorResult.OK
    while result == Gst.IteratorResult.OK:
        result, value = gst_iterator.next()
        if result == Gst.IteratorResult.OK:
            yield value
        elif result == Gst.IteratorResult.ERROR:
            raise RuntimeError("Iteration Error")
        elif result == Gst.IteratorResult.RESYNC:
            raise RuntimeError("Iteration Resync")
