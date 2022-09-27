import os
import queue
import random
import signal
import subprocess
import sys
from contextlib import contextmanager

from .utils import named_temporary_directory


class XFailedToStartError(Exception):
    pass


def _start_x(*args, **kwargs):
    """
    Implements the X startup notification protocol.  From man Xorg:

    > When the server starts, it checks to see if it has inherited SIGUSR1 as
    > SIG_IGN instead of the usual SIG_DFL.   In this case, the server sends a
    > SIGUSR1 to its parent process after it has set up the various connection
    > schemes.
    """
    q = queue.Queue()

    def on_signal(signo, _stack_frame):
        q.put(signo)

    orig_handler = {}
    for x in [signal.SIGUSR1, signal.SIGCHLD]:
        orig_handler[x] = signal.signal(x, on_signal)

    xorg = subprocess.Popen(  # pylint:disable=subprocess-popen-preexec-fn
        preexec_fn=lambda: signal.signal(signal.SIGUSR1, signal.SIG_IGN),
        *args, **kwargs)

    try:
        while True:
            signo = q.get(True, 10)
            if signo == signal.SIGUSR1 or xorg.poll() is not None:
                return xorg
    except:
        xorg.kill()
        raise
    finally:
        for signo, handler in orig_handler.items():
            signal.signal(signo, handler)


@contextmanager
def x_server(width, height, verbose=False):
    with open(os.path.dirname(__file__) + '/xorg.conf.in',
              encoding='utf-8') as f:
        xorg_conf_template = f.read()

    # This is a racy way of finding a free X display but is a lot simpler than
    # the alternatives:
    display_no = None
    for display_no in sorted(range(10, 100), key=lambda k: random.random()):
        if not os.path.exists('/tmp/.X11-unix/X%i' % display_no):
            break
    else:
        raise XFailedToStartError(
            "No available X display numbers (tried displays 10 to 99)")

    with named_temporary_directory(prefix='stbt-xorg-') as tmp:

        with open('%s/xorg.conf' % tmp, 'w', encoding='utf-8') as xorg_conf:
            xorg_conf.write(xorg_conf_template.format(
                width=width, height=height))

        if verbose:
            kwargs = {'stdout': subprocess.DEVNULL,
                      'stderr': subprocess.DEVNULL}
        else:
            kwargs = {}
        xorg = _start_x(
            ['Xorg', '-noreset', '+extension', 'GLX',
             '+extension', 'RANDR', '+extension', 'RENDER',
             '-config', 'xorg.conf', '-logfile', './xorg.log',
             '-nolisten', 'tcp', ':%i' % display_no],
            cwd=tmp, stdin=subprocess.DEVNULL, close_fds=True, **kwargs)
        try:
            if xorg.poll() is not None:
                raise XFailedToStartError(
                    "Failed to start X: Exited with status %i"
                    % xorg.returncode)
            yield ":%i" % display_no
        finally:
            if xorg.poll() is None:
                xorg.terminate()
                xorg.wait()
            if verbose:
                sys.stderr.write("\nxorg.log:\n")
                with open("%s/xorg.log" % tmp, "r", encoding="utf-8") as log:
                    sys.stderr.write("".join(log.readlines()))
