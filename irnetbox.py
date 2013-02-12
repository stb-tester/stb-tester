# -*- coding: utf-8 -*-

"""Python module to control the RedRat irNetBox-III infrared emitter.

Author: David Rothlisberger <david@rothlis.net>
Copyright 2012 YouView TV Ltd.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/drothlis/stb-tester/blob/master/LICENSE for details).

The irNetBox-III is a network-controlled infrared emitter:
http://www.redrat.co.uk/products/irnetbox.html

This module only supports version III of the irNetBox hardware.

"§" section numbers in the function docstrings are from "The irNetBox
Network Control Protocol":
http://www.redrat.co.uk/products/IRNetBox_Comms-V3.0.pdf

Thanks to Chris Dodge at RedRat for friendly and prompt answers to all my
questions.

Classes:

IRNetBox -- An instance of IRNetBox holds a TCP connection to the device.
Note that the device only accepts one TCP connection at a time, so keep this
as short-lived as possible. For example:

    with irnetbox.IRNetBox("192.168.0.10") as ir:
        ir.power_on()
        ir.irsend_raw(port=1, power=100, data=binascii.unhexlify("000174F..."))

RemoteControlConfig -- Holds infrared signal data from a config file produced
by RedRat's "IR Signal Database Utility". Example usage (where "POWER" is a
signal defined in the config file):

    rcu = irnetbox.RemoteControlConfig("my-rcu.irnetbox.config")
    ir.irsend_raw(port=1, power=100, data=rcu["POWER"])

"""

import binascii
import errno
import random
import re
import socket
import struct
import sys
import time


class IRNetBox:
    def __init__(self, hostname):
        port = 10001  # §5
        for i in range(6):
            try:
                self._socket = socket.socket()
                self._socket.connect((hostname, port))
                break
            except socket.error as e:
                if e.errno == errno.ECONNREFUSED and i < 5:
                    delay = 0.1 * 2**i
                    sys.stderr.write(
                        "Connection to irNetBox '%s:%d' refused; "
                        "retrying in %.2fs.\n" %
                        (hostname, port, delay))
                    time.sleep(delay)
                else:
                    raise
        self._responses = _read_responses(self._socket)
        self.irnetbox_model = 0
        self._get_version()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self._socket.close()

    def power_on(self):
        """Power on the irNetBox device (§5.2.3).

        §5.2.3 calls this "power to the CPLD device"; the irNetBox-III doesn't
        have a CPLD, but according to Chris Dodge @ RedRat, this is now "power
        on the whole irNetBox".

        """
        self._send(MessageTypes.POWER_ON)

    def power_off(self):
        """Put the irNetBox in low-power standby mode (§5.2.3).

        In low power mode the LEDs on the front will be doing the Cylon
        pattern.

        """
        self._send(MessageTypes.POWER_OFF)

    def reset(self):
        """Reset the CPLD"""
        self._send(
            MessageTypes.CPLD_INSTRUCTION,
            struct.pack("B", 0x00))

    def indicators_on(self):
        """Enable LED indicators on the front panel (§5.2.4)."""
        self._send(
            MessageTypes.CPLD_INSTRUCTION,
            struct.pack("B", 0x17))

    def indicators_off(self):
        """Disable LED indicators on the front panel (§5.2.4)."""
        self._send(
            MessageTypes.CPLD_INSTRUCTION,
            struct.pack("B", 0x18))

    def irsend_raw(self, port, power, data):
        """Output the IR data on the given port at the set power (§6.1.1).

        * `port` is a number between 1 and 16.
        * `power` is a number between 1 and 100.
        * `data` is a byte array as exported by the RedRat Signal DB Utility.

        """
        if self.irnetbox_model == NetBoxTypes.MK2:
            self.reset()
            self.indicators_on()
            self._send(MessageTypes.SET_MEMORY)
            self._send(MessageTypes.CPLD_INSTRUCTION, struct.pack("B", 0x00))
            if power < 33:
                self._send(
                    MessageTypes.CPLD_INSTRUCTION,
                    struct.pack("B", port + 1))
            elif power < 66:
                self._send(
                    MessageTypes.CPLD_INSTRUCTION,
                    struct.pack("B", port + 31))
            else:
                self._send(
                    MessageTypes.CPLD_INSTRUCTION,
                    struct.pack("B", port + 1))
                self._send(
                    MessageTypes.CPLD_INSTRUCTION,
                    struct.pack("B", port + 31))
            self._send(MessageTypes.DOWNLOAD_SIGNAL, data)
            self._send(MessageTypes.OUTPUT_IR_SIGNAL)
            self.reset()
        elif self.irnetbox_model == NetBoxTypes.MK3:
            ports = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
            ports[port-1] = power
            sequence_number = random.randint(0, 2**16 - 1)
            delay = 0  # use the default delay of 100ms
            self._send(
                MessageTypes.OUTPUT_IR_ASYNC,
                struct.pack(
                    ">HH16s%ds" % len(data),
                    sequence_number,
                    delay,
                    struct.pack("16B", *ports),
                    data))
        elif self.irnetbox_model == NetBoxTypes.MK1:
            raise Exception("IRNetBox MK1 not supported")

    def _send(self, message_type, message_data=""):
        self._socket.sendall(_message(message_type, message_data))
        response_type, response_data = self._responses.next()
        if response_type == MessageTypes.ERROR:
            raise Exception("IRNetBox returned ERROR")
        if response_type == MessageTypes.DEVICE_VERSION:
            self.irnetbox_model, = struct.unpack(
                '<H', response_data[10:12])  # == §5.2.6's payload_data[8:10]

    def _get_version(self):
        self._send(MessageTypes.DEVICE_VERSION)


class RemoteControlConfig:
    def __init__(self, filename):
        self._data = _parse_config(open(filename))

    def __getitem__(self, key):
        return self._data[key]


class MessageTypes:
    """§5.2"""
    ERROR = 0x01
    POWER_ON = 0x05
    POWER_OFF = 0x06
    CPLD_INSTRUCTION = 0x07
    DEVICE_VERSION = 0x09
    SET_MEMORY = 0x10
    DOWNLOAD_SIGNAL = 0x11
    OUTPUT_IR_SIGNAL = 0x12
    OUTPUT_IR_ASYNC = 0x30
    IR_ASYNC_COMPLETE = 0x31


MESSAGE_NAMES = {
    MessageTypes.ERROR: "ERROR",
    MessageTypes.POWER_ON: "POWER_ON",
    MessageTypes.POWER_OFF: "POWER_OFF",
    MessageTypes.CPLD_INSTRUCTION: "CPLD_INSTRUCTION",
    MessageTypes.OUTPUT_IR_ASYNC: "OUTPUT_IR_ASYNC",
    MessageTypes.IR_ASYNC_COMPLETE: "IR_ASYNC_COMPLETE",
}


class NetBoxTypes:
    """§5.2.6"""
    MK1 = 2
    MK2 = 7
    MK3 = 8


def _message(message_type, message_data):
    # §5.1. Message Structure: Host to irNetBox
    #
    # '#'              byte     The '#' character indicates to the control
    #                           microprocessor the start of a message.
    # Message length   ushort   The length of the data section of this message.
    # Message type     byte     One of the values listed below.
    # Data             byte[]   Any data associated with this type of message.
    #
    # A ushort value is a 16-bit unsigned integer in big-endian format.
    #
    return struct.pack(
        ">cHB%ds" % len(message_data),
        "#",
        len(message_data),
        message_type,
        message_data)


def _read_responses(stream):
    """Generator that splits stream into (type, data) tuples."""

    # §5.1. Message Structure: irNetBox to Host
    #
    # Message length   ushort   The length of the data section of this message.
    # Message type     byte     Contains either:
    #                           a) The same value as the original message from
    #                              the host, or
    #                           b) A value (0x01) indicating "Error".
    # Data             byte[]   Any data associated with this type of message.
    #
    buf = ""
    while True:
        s = stream.recv(4096)
        if len(s) == 0:
            break
        buf += s
        while len(buf) >= 3:
            data_len, = struct.unpack(">H", buf[0:2])
            if len(buf) < 3 + data_len:
                break
            response_type, response_data = struct.unpack(
                ">B%ds" % data_len,
                buf[2 : 3+data_len])
            if response_type != MessageTypes.IR_ASYNC_COMPLETE:
                yield response_type, response_data
            buf = buf[3+data_len :]


def _parse_config(file):
    """Read irNetBox configuration file.

    Which is produced by RedRat's (Windows-only) "IR Signal Database Utility".

    This doesn't support config files with "double signals" (where 2 different
    signals were recorded from alternate presses of the same button on the
    remote control unit).

    """
    d = {}
    for line in file:
        fields = re.split("[\t ]+", line.rstrip(), maxsplit=3)
        if len(fields) == 4:
            name, type_, max_num_lengths, data = fields
            if type_ == "MOD_SIG":
                d[name] = binascii.unhexlify(data)
    return d


# Tests
#===========================================================================

def test_that_read_responses_doesnt_hang_on_incomplete_data():
    import StringIO

    data = "abcdefghij"
    m = struct.pack(
        ">HB%ds" % len(data),
        len(data),
        0x01,
        data)

    assert _read_responses(_FileToSocket(StringIO.StringIO(m))).next() == \
        (0x01, data)
    try:
        _read_responses(_FileToSocket(StringIO.StringIO(m[:5]))).next()
    except StopIteration:
        pass
    else:
        assert False  # expected StopIteration exception


def test_that_parse_config_understands_redrat_format():
    import StringIO

    f = StringIO.StringIO(re.sub("^ +", "", flags=re.MULTILINE, string=
        """Device TestRCU

        Note: The data is of the form <signal name> MOD_SIG <max_num_lengths> <byte_array_in_ascii_hex>.

        DOWN	MOD_SIG	16 000174F5FF60000000060000004802450222F704540D12116A464F0000000000000000000000000000000000000000000102020202020202020202020202020202020202020202020202030202020202020202020202030202020202020203020202030203020202030203020302020203027F0004027F

        UP	MOD_SIG	16 000174FAFF60000000050000004803457422F7045A0D13116A00000000000000000000000000000000000000000000000102020202020202020202020202020202020202020202020202030202020202020203020202020202020202020203020202020203020302030203020302020203027F0004027F
        """))
    config = _parse_config(f)
    assert config["DOWN"].startswith("\x00\x01\x74\xF5")
    assert config["UP"].startswith("\x00\x01\x74\xFA")


class _FileToSocket:
    """Makes something File-like behave like a Socket for testing purposes.

    >>> import StringIO
    >>> s = _FileToSocket(StringIO.StringIO('Hello'))
    >>> s.recv(3)
    'Hel'
    >>> s.recv(3)
    'lo'
    >>> s.recv(3)
    ''
    """
    def __init__(self, f):
        self.file = f

    def recv(self, bufsize, flags=0):
        return self.file.read(bufsize)
