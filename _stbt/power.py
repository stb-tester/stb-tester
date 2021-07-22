import errno
import os
import re
import time

from _stbt.config import ConfigurationError


def uri_to_power_outlet(uri):
    remotes = [
        (r'none', _NoOutlet),
        (r'file:(?P<filename>[^:]+)', _FileOutlet),
        (r'aten:(?P<address>[^: ]+):(?P<outlet>[^: ]+)', _ATEN_PE6108G),
        (r'rittal:(?P<address>[^: ]+):(?P<outlet_no>[^: ]+)'
         ':(?P<community>[^: ]+)', _RittalSnmpPower),
        (r'(?P<model>pdu|ipp|testfallback):(?P<hostname>[^: ]+)'
         ':(?P<outlet>[^: ]+)', _ShellOutlet),
        (r'aviosys-8800-pro(:(?P<filename>[^:]+))?', _new_aviosys_8800_pro),
    ]
    for regex, factory in remotes:
        m = re.match(regex, uri, re.VERBOSE | re.IGNORECASE)
        if m:
            return factory(**m.groupdict())
    raise ConfigurationError('Invalid power outlet URI: "%s"' % uri)


class _NoOutlet(object):
    def set(self, power):
        if not power:
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
        return {b'ON': True, b'OFF': False}[power]


class _Aviosys8800Pro(object):
    """Documentation of the serial IO protocol found on the Aviosys website:

    http://www.aviosys.com/downloads/manuals/power/USB%20Net%20Power%208800%20Pro%20Manual_EN.pdf

    >>> f = _FakeAviosys8800ProSerial()
    >>> u = _Aviosys8800Pro(f)
    >>> u.get()
    False
    >>> u.set(True)
    >>> f.is_on
    True
    >>> u.get()
    True
    >>> u.set(False)
    >>> f.is_on
    False
    >>> u.get()
    False
    """
    def __init__(self, device):
        """Device is a file-like serial device"""
        self.device = device

    def set(self, power):
        self.device.write("p1=%i\n" % power)
        self.device.readline()

    def get(self):
        self.device.write("readio\n")
        self.device.readline()
        response = self.device.readline()
        if response == 'IO:5\r\n':
            return True
        elif response == 'IO:0\r\n':
            return False
        else:
            raise RuntimeError(
                "Unexpected response from Aviosys 8800 Pro: \"%s\""
                % response.strip())


def _new_aviosys_8800_pro(filename='/dev/ttyACM0'):
    import serial
    return _Aviosys8800Pro(serial.Serial(filename, baudrate=19200))


class _FakeAviosys8800ProSerial(object):
    r"""Used for testing the below _UsbPower8800Pro class.  Behaviour determined
    in interactive ipython shell and reproduced here:

    >>> fup = _FakeAviosys8800ProSerial()
    >>> fup.is_on
    False
    >>> fup.write("p1=1\n")
    5
    >>> fup.readline()
    'p1=1\r\n'
    >>> fup.is_on
    True
    >>> fup.write("p1=0\n")
    5
    >>> fup.readline()
    'z>p1=0\r\n'
    >>> fup.is_on
    False
    >>> fup.write('readio\n')
    7
    >>> fup.readline()
    'z>readio\r\n'
    >>> fup.readline()
    'IO:0\r\n'
    >>> fup.write("p1=1junkjunk\n")
    13
    >>> fup.readline()
    'z>p1=1junkjunk\r\n'
    >>> fup.write('readiojunk\n')
    11
    >>> fup.readline()
    'z>readiojunk\r\n'
    >>> fup.readline()
    'IO:5\r\n'
    """
    def __init__(self):
        self.is_on = False
        self.remainder = ""
        self.outbuf = ""
        self.inbuf = ""

    def readline(self):
        idx = self.outbuf.find('\n')
        assert idx >= 0, "FakeUsbPower8000 would have blocked"

        out, self.outbuf = self.outbuf[:idx + 1], self.outbuf[idx + 1:]
        return out

    def respond(self, text):
        self.outbuf += text

    def write(self, data):
        self.inbuf += data

        while '\n' in self.inbuf:
            idx = self.inbuf.find('\n')
            line, self.inbuf = self.inbuf[:idx], self.inbuf[idx + 1:]

            if len(line) >= 4 and line[:3] == "p1=":
                if line[3] == '0':
                    self.is_on = False
                elif line[3] == '1':
                    self.is_on = True
            self.respond(line + '\r\n')
            if line.startswith('readio'):
                self.respond('IO:%i\r\n' % (5 if self.is_on else 0))
            self.respond('z>')

        return len(data)


class _RittalSnmpPower(object):
    """
    Tested with the DK 7955.310.  SNMP OIDs may be different on other devices.
    """
    def __init__(self, address, outlet_no, community):
        outlet_no = int(outlet_no)
        index = outlet_no - 1
        if index < 0:
            raise ValueError("Invalid outlet_no %i.  Min outlet no is 1" %
                             outlet_no)
        self._snmp = _SnmpInteger(
            address, "1.3.6.1.4.1.2606.7.4.2.2.1.11.1.%i" % (52 + index * 7),
            community)

    def get(self):
        return bool(self._snmp.get())

    def set(self, power):
        if self._snmp.set(int(bool(power))) != int(bool(power)):
            raise RuntimeError("Setting power failed with unknown error")


class _ATEN_PE6108G(object):
    """Class to control the ATEN PDU using pysnmp module. """

    def __init__(self, address, outlet):
        outlet = int(outlet)
        outlet_offset = 1 if outlet <= 8 else 2
        self._snmp = _SnmpInteger(
            address, "1.3.6.1.4.1.21317.1.3.2.2.2.2.%i.0" % (
                outlet + outlet_offset),
            community='administrator')

    def set(self, power):
        new_state = self._snmp.set(2 if power else 1)

        # ATEN PE6108G outlets take between 4-8 seconds to power on
        for _ in range(12):
            time.sleep(1)
            if self._snmp.get() == new_state:
                return
        raise RuntimeError(
            "Timeout waiting for outlet to power {}".format(
                "ON" if power else "OFF"))

    def get(self):
        result = self._snmp.get()
        # 3 represents moving between states
        return {3: False, 2: True, 1: False}[result]


class _SnmpInteger(object):
    def __init__(self, address, oid, community):
        from pysnmp.entity.rfc3413.oneliner.cmdgen import UdpTransportTarget
        self.oid = oid
        self._community = community
        if ':' in address:
            address, port = address.split(address, 2)
        else:
            port = "161"
        self._transport = UdpTransportTarget((address, int(port)))

    def set(self, value):
        return self._cmd(value)

    def get(self):
        return self._cmd(None)

    def _cmd(self, value):
        from pysnmp.entity.rfc3413.oneliner import cmdgen
        from pysnmp.proto.rfc1905 import NoSuchObject
        from pysnmp.proto.rfc1902 import Integer

        command_generator = cmdgen.CommandGenerator()

        if value is None:  # `status` command
            error_ind, _, _, var_binds = command_generator.getCmd(
                cmdgen.CommunityData(self._community),
                self._transport,
                self.oid)
        else:
            error_ind, _, _, var_binds = command_generator.setCmd(
                cmdgen.CommunityData(self._community),
                self._transport,
                (self.oid, Integer(value)))

        if error_ind is not None:
            raise RuntimeError("SNMP Error ({})".format(error_ind))

        _, result = var_binds[0]

        if isinstance(result, NoSuchObject):
            raise RuntimeError("No such outlet")

        if not isinstance(result, Integer):
            raise RuntimeError("Unexpected result ({})".format(result))

        return int(result)
