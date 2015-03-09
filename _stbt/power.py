#!/usr/bin/python

import errno
import os
import re

from _stbt.config import ConfigurationError


def uri_to_power_outlet(uri):
    remotes = [
        (r'none', _NoOutlet),
        (r'file:(?P<filename>[^:]+)', _FileOutlet),
        (r'(?P<model>pdu|ipp|aten|testfallback):(?P<hostname>[^: ]+)'
         ':(?P<outlet>[^: ]+)', _ShellOutlet),
    ]
    for regex, factory in remotes:
        m = re.match(regex, uri, re.VERBOSE | re.IGNORECASE)
        if m:
            return factory(**m.groupdict())
    raise ConfigurationError('Invalid power outlet URI: "%s"' % uri)


class _NoOutlet(object):
    def set(self, power):
        if power == False:
            raise RuntimeError(
                "Cannot disable power: no power outlet configured")

    def get(self):
        # If we can't turn it off, it must be on
        return True


class _FileOutlet(object):
    """Power outlet useful for testing"""
    def __init__(self, filename):
        self.filename = filename

    def set(self, power):
        with open(self.filename, 'w') as f:
            f.write(['0', '1'][power])

    def get(self):
        try:
            with open(self.filename, 'r') as f:
                return bool(int(f.read(1)))
        except IOError as e:
            if e.errno == errno.ENOENT:
                return True
            else:
                raise


class _ShellOutlet(object):
    """
    stbt-power used to be written in bash, supporting three different types of
    hardware.  This is a wrapper to allow the old bash script to continue
    working until it can be removed entirely.
    """
    def __init__(self, model, hostname, outlet=None):
        uri = '%s:%s:%s' % (model, hostname, outlet)
        self.cmd = ['bash', os.path.dirname(__file__) + "/stbt-power.sh",
                    '--power-outlet=%s' % uri]

    def set(self, power):
        import subprocess
        subprocess.check_call(self.cmd + [["off", "on"][power]])

    def get(self):
        import subprocess
        power = subprocess.check_output(self.cmd + ["status"]).strip()
        return {'ON': True, 'OFF': False}[power]
