import pygst  # gstreamer
pygst.require("0.10")
import gst
import sys

def hauppauge(device="/dev/video0"):
    """Gstreamer source configuration for Hauppauge HD PVR
    (model 49001 LF Rev F2).
    """
    return " ! ".join([
            "v4l2src device=%s" % device, # Video-for-Linux-2 input device.
            "mpegtsdemux",  # Demultiplex the mpeg transport stream.
            "video/x-h264", # We only care about the video -- and in fact the aac decoder was causing some problems.
            "decodebin",    # A gstreamer "bin" is a set of components packaged up for easy use. This one decodes (among other things) H.264.
            ])


def save_frame(buf, filename):
    '''Save a gstreamer buffer to the specified file in png format.'''
    pipeline = gst.parse_launch(" ! ".join([
                'appsrc name="src" caps="%s"' % buf.get_caps(),
                'pngenc',
                'filesink location="%s"' % filename,
                ]))
    src, = [x for x in pipeline.elements() if x.get_name() == 'src']
    # This is actually a (synchronous) method call to push-buffer:
    src.emit('push-buffer', buf)
    src.emit('end-of-stream')
    pipeline.set_state(gst.STATE_PLAYING)
    msg = pipeline.get_bus().poll(
        gst.MESSAGE_ERROR | gst.MESSAGE_EOS, 25 * gst.SECOND);
    pipeline.set_state(gst.STATE_NULL)
    if msg.type == gst.MESSAGE_ERROR:
        (e, debug) = msg.parse_error()
        raise RuntimeError(e.message)


class VirtualRemote:
    """Send a key-press to a set-top box running a VirtualRemote listener.

        control = VirtualRemote("192.168.0.123")
        control.press("MENU")
    """
    def __init__(self, stb):
        self.stb = stb
        self.port = 2033

    def press(self, key):
        import socket
        s = socket.socket()
        s.connect((self.stb, self.port))
        s.send("D\t%s\n\0U\t%s\n\0" % (key, key)) # send key Down, then key Up.
        debug("Pressed " + key)


def read_records(stream, sep):
    r"""Generator that splits stream into records given a separator

    >>> import StringIO
    >>> s = StringIO.StringIO('hello\n\0This\n\0is\n\0a\n\0test\n\0')
    >>> list(read_records(s, '\n\0'))
    ['hello', 'This', 'is', 'a', 'test']
    """
    buf = ""
    l = len(sep)
    while True:
        s = stream.recv(4096)
        if len(s) == 0:
            break
        buf += s
        cmds = buf.split(sep)
        buf = cmds[-1]
        for i in cmds[:-1]:
            yield i


def key_reader(cmd_iter):
    r"""Converts virtual remote records into list of keys

    >>> list(key_reader(['D\tHELLO', 'U\tHELLO']))
    ['HELLO']
    >>> list(key_reader(['D\tCHEESE', 'D\tHELLO', 'U\tHELLO', 'U\tCHEESE']))
    ['HELLO', 'CHEESE']
    """
    for i in cmd_iter:
        (action, key) = i.split('\t')
        if action == 'U':
            yield key


def virtual_remote_listen(listenport=2033):
    """Waits for a VirtualRemote to connect, and returns an iterator yielding
    keypresses."""
    import socket
    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serversocket.bind(('', listenport))
    serversocket.listen(5)
    sys.stderr.write("Waiting for connection from virtual remote control port %d...\n" % listenport)
    (connection, address) = serversocket.accept()
    sys.stderr.write("Accepted connection from %s\n" % str(address))
    return key_reader(read_records(connection, '\n\0'))


def debug(s):
    sys.stderr.write(sys.argv[0] + ": " + str(s) + "\n")
