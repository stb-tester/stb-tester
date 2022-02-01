# -*- coding: utf-8 -*-

"""Python module to control the RedRat irNetBox infrared emitter.

Author: David Rothlisberger <david@rothlis.net>
Copyright 2012 YouView TV Ltd and contributors.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).

The irNetBox is a network-controlled infrared emitter:
http://www.redrat.co.uk/products/irnetbox.html

This module only supports versions II and III of the irNetBox hardware.

"§" section numbers in the function docstrings are from "The irNetBox
Network Control Protocol":
http://www.redrat.co.uk/products/IRNetBox_Comms-V3.0.pdf

Thanks to Chris Dodge at RedRat for friendly and prompt answers to all my
questions, and to Emmett Kelly for the mk-II implementation.

Classes:

IRNetBox
  An instance of IRNetBox holds a TCP connection to the device.

  Note that the device only accepts one TCP connection at a time, so keep this
  as short-lived as possible. For example::

    with irnetbox.IRNetBox("192.168.0.10") as ir:
        ir.power_on()
        ir.irsend_raw(port=1, power=100, data=binascii.unhexlify("000174F..."))

  Or run './irnetbox-proxy', which accepts multiple connections and forwards
  requests on to a real irNetBox.

RemoteControlConfig
  Holds infrared signal data from a config file produced by RedRat's "IR Signal
  Database Utility". Example usage (where "POWER" is a signal defined in the
  config file)::

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


class IRNetBox():
    def __init__(self, hostname, port=10001):  # §5
        for i in range(6):
            try:
                self._socket = socket.socket()
                self._socket.settimeout(10)
                self._socket.connect((hostname, port))
                break
            except socket.error as e:
                if e.errno == errno.ECONNREFUSED and i < 5:
                    delay = 0.1 * (2 ** i)
                    sys.stderr.write(
                        "Connection to irNetBox '%s:%d' refused; "
                        "retrying in %.2fs.\n" %
                        (hostname, port, delay))
                    time.sleep(delay)
                else:
                    raise
        self._responses = _read_responses(self._socket)
        self.irnetbox_model = 0
        self.ports = 16
        self._get_version()

    def __enter__(self):
        return self

    def __exit__(self, ex_type, ex_value, ex_traceback):
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

        * `port` is a number between 1 and 16 (or 1 and 4 for RedRat X).
        * `power` is a number between 1 and 100.
        * `data` is a byte array as exported by the RedRat Signal DB Utility.

        """
        if self.irnetbox_model == NetBoxTypes.MK1:
            raise Exception("IRNetBox MK1 not supported")
        elif self.irnetbox_model == NetBoxTypes.MK2:
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
        else:
            ports = [0] * self.ports
            ports[port - 1] = power
            sequence_number = random.randint(0, (2 ** 16) - 1)
            delay = 0  # use the default delay of 100ms
            self._send(
                MessageTypes.OUTPUT_IR_ASYNC,
                struct.pack(
                    ">HH{0}s{1}s".format(self.ports, len(data)),
                    sequence_number,
                    delay,
                    struct.pack("{}B".format(self.ports), *ports),
                    data))

    def _send(self, message_type, message_data=b""):
        self._socket.sendall(_message(message_type, message_data))
        response_type, response_data = next(self._responses)
        if response_type == MessageTypes.ERROR:
            raise Exception("IRNetBox returned ERROR")
        if response_type != message_type:
            raise Exception(
                "IRNetBox returned unexpected response type %d to request %d" %
                (response_type, message_type))
        if response_type == MessageTypes.OUTPUT_IR_ASYNC:
            sequence_number, error_code, ack = struct.unpack(
                # Sequence number in the ACK message is defined as big-endian
                # in §5.1 and §6.1.2, but due to a known bug it is
                # little-endian.
                '<HBB', response_data)
            if ack == 1:
                async_type, async_data = next(self._responses)
                if async_type != MessageTypes.IR_ASYNC_COMPLETE:
                    raise Exception(
                        "IRNetBox returned unexpected message %d" % async_type)
                (async_sequence_number,) = struct.unpack(">H", async_data[:2])
                if async_sequence_number != sequence_number:
                    raise Exception(
                        "IRNetBox returned message IR_ASYNC_COMPLETE "
                        "with unexpected sequence number %d (expected %d)" %
                        (async_sequence_number, sequence_number))
            else:
                raise Exception(
                    "IRNetBox returned NACK (error code: %d)" % error_code)
        if response_type == MessageTypes.DEVICE_VERSION:
            self.irnetbox_model, = struct.unpack(
                '<H', response_data[10:12])  # == §5.2.6's payload_data[8:10]

    def _get_version(self):
        self._send(MessageTypes.DEVICE_VERSION)
        self.ports = 4 if self.irnetbox_model == NetBoxTypes.RRX else 16


def RemoteControlConfig(filename):
    return _parse_config(open(filename, "rb"))


class MessageTypes():
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


class NetBoxTypes():
    """§5.2.6"""
    MK1 = 2
    MK2 = 7
    MK3 = 8
    MK4 = 12
    RRX = 13


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
        b"#",
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
    buf = b""
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
                buf[2:(3 + data_len)])
            yield response_type, response_data
            buf = buf[(3 + data_len):]


def _parse_config(config_file):
    """Read irNetBox configuration file.

    Which is produced by RedRat's (Windows-only) "IR Signal Database Utility".
    """
    d = {}
    for line in config_file:
        fields = re.split(b"[\t ]+", line.rstrip(), maxsplit=4)
        if len(fields) == 4:
            # (name, type, max_num_lengths, data)
            name, type_, _, data = fields
            if type_ == b"MOD_SIG":
                d[name.decode("utf-8")] = binascii.unhexlify(data)
        if len(fields) == 5:
            # "Double signals" where pressing the button on the remote control
            # alternates between signal1 & signal2. We'll always send signal1,
            # but that shouldn't matter.
            # (name, type, signal1 or signal2, max_num_lengths, data)
            name, type_, signal, _, data = fields
            if type_ == b"DMOD_SIG" and signal == b"signal1":
                d[name.decode("utf-8")] = binascii.unhexlify(data)
    return d


# Tests
# ===========================================================================

def test_that_read_responses_doesnt_hang_on_incomplete_data():
    import io

    data = b"abcdefghij"
    m = struct.pack(
        ">HB%ds" % len(data),
        len(data),
        0x01,
        data)

    assert next(_read_responses(_FileToSocket(io.BytesIO(m)))) == \
        (0x01, data)
    try:
        next(_read_responses(_FileToSocket(io.BytesIO(m[:5]))))
    except StopIteration:
        pass
    else:
        assert False  # expected StopIteration exception


def test_that_parse_config_understands_redrat_format():
    import io

    f = io.BytesIO(
        re.sub(
            b"^ +", b"", flags=re.MULTILINE,
            string=b"""Device TestRCU

            Note: The data is of the form <signal name> MOD_SIG <max_num_lengths> <byte_array_in_ascii_hex>.

            DOWN	MOD_SIG	16 000174F5FF60000000060000004802450222F704540D12116A464F0000000000000000000000000000000000000000000102020202020202020202020202020202020202020202020202030202020202020202020202030202020202020203020202030203020202030203020302020203027F0004027F

            UP	MOD_SIG	16 000174FAFF60000000050000004803457422F7045A0D13116A00000000000000000000000000000000000000000000000102020202020202020202020202020202020202020202020202030202020202020203020202020202020202020203020202020203020302030203020302020203027F0004027F

            RED	DMOD_SIG	signal1	16 0002BCAFFF5A0000000300000024010E3206E60DB1000000000000000000000000000000000000000000000000000000010101010200020002000200020101017F00010101010200020002000200020101017F
            RED	DMOD_SIG	signal2	16 0002BCE3FF5A0000000300000020010E2C0DB006EC00000000000000000000000000000000000000000000000000000001000100010001000100010202027F0001000100010001000100010202027F
            """))
    config = _parse_config(f)
    assert config["DOWN"].startswith(b"\x00\x01\x74\xF5")
    assert config["UP"].startswith(b"\x00\x01\x74\xFA")
    assert config["RED"].startswith(b"\x00\x02\xBC\xAF")


class _FileToSocket():
    """Makes something File-like behave like a Socket for testing purposes.

    >>> import io
    >>> s = _FileToSocket(io.BytesIO(b'Hello'))
    >>> s.recv(3)
    'Hel'
    >>> s.recv(3)
    'lo'
    >>> s.recv(3)
    ''
    """

    def __init__(self, f):
        self.file = f

    def recv(self, bufsize, flags=0):  # pylint:disable=unused-argument
        return self.file.read(bufsize)
