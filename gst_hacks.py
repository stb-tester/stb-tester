from contextlib import contextmanager
import ctypes

from gi.repository import Gst  # pylint: disable=E0611


# Here we are using ctypes to call `gst_buffer_map` and `gst_buffer_unmap`
# because PyGObject does not properly expose struct GstMapInfo (see
# [bz #678663]).  Apparently this is fixed upstream but we are still awaiting
# an upstream release (Mar 2014).  Hopefully this can be removed in the future.


class _GstMapInfo(ctypes.Structure):
    _fields_ = [("memory", ctypes.c_void_p),   # GstMemory *memory
                ("flags", ctypes.c_int),       # GstMapFlags flags
                ("data", ctypes.POINTER(ctypes.c_byte)),    # guint8 *data
                ("size", ctypes.c_size_t),     # gsize size
                ("maxsize", ctypes.c_size_t)]  # gsize maxsize

_GstMapInfo_p = ctypes.POINTER(_GstMapInfo)

_libgst = ctypes.CDLL("libgstreamer-1.0.so.0")
_libgst.gst_buffer_map.argtypes = [ctypes.c_void_p, _GstMapInfo_p, ctypes.c_int]
_libgst.gst_buffer_map.restype = ctypes.c_int

_libgst.gst_buffer_unmap.argtypes = [ctypes.c_void_p, _GstMapInfo_p]
_libgst.gst_buffer_unmap.restype = None


@contextmanager
def map_gst_buffer(buf, flags):
    if not isinstance(buf, Gst.Buffer):
        raise TypeError("map_gst_buffer must take a Gst.Buffer")
    if flags & Gst.MapFlags.WRITE and not buf.mini_object.is_writable():
        raise ValueError(
            "Writable array requested but buffer is not writeable")

    # hashing a GObject actually gives the address (pointer) of the C struct
    # that backs it!:
    pbuffer = hash(buf)
    mapping = _GstMapInfo()
    success = _libgst.gst_buffer_map(pbuffer, mapping, flags)
    if not success:
        raise RuntimeError("Couldn't map buffer")
    try:
        yield ctypes.cast(
            mapping.data, ctypes.POINTER(ctypes.c_byte * mapping.size)).contents
    finally:
        _libgst.gst_buffer_unmap(pbuffer, mapping)


def test_map_buffer_reading_data():
    Gst.init([])

    b = Gst.Buffer.new_wrapped("hello")
    with map_gst_buffer(b, Gst.MapFlags.READ) as a:
        assert 'hello' == ''.join(chr(x) for x in a)


def test_map_buffer_modifying_data():
    Gst.init([])

    b = Gst.Buffer.new_wrapped("hello")
    with map_gst_buffer(b, Gst.MapFlags.WRITE | Gst.MapFlags.READ) as a:
        a[2] = 1

    assert b.extract_dup(0, 5) == "he\x01lo"
