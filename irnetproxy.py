#!/usr/bin/env python2.7

"""
A network proxy for RedRat irNetBox MK-III infra-red blaster modules.
Based on the protocol document:

http://www.redrat.co.uk/products/IRNetBox_Comms-V3.X.pdf

This script allows many clients to connect to the device, and use the ports
concurrently.  **Note**, this only makes sense for the Asynchronous IO
Output Commands, other commands will be run synchronously.

Usage
-----

```
$ irnetproxy -r <irNetBox address>
```

OR

```
$ irnetproxy --irnetbox-addresss <irNetBox address> --irnetbox-port 10001\
      --listen-port 10001 --listen-address 127.0.0.1 -vv

> Listening for connections on 127.0.0.1:10001
```

Features
--------

 - Session multiplexing: irnetproxy dynamically maps Asyncronous Sequence IDs
 on the fly, meaning that multiple clients can use the same Sequence ID
 concurrently, and the irnet box will continue to work.  Both the command
 acknowledgement, and the subsequent Async complete message are always routed
 to the correct client.

 - On/Off management: irnetproxy will silently accept the on and off messages
 (5 and 6).  A standard ACK response is returned to the client, but the command
 is never sent to the device. This allows multiple scripts to try to turn off
 the device while other devices use it.  irnetproxy issues the ON command when
 it connects, and issues an OFF command when it is stopped.

"""

import cStringIO as StringIO
import argparse
import itertools
import select
import socket
import struct
import sys
import traceback


def safe_recv(sock, num):
    in_buffer = StringIO.StringIO()
    while num:
        packet = sock.recv(num)
        if packet == '':
            raise SocketClosed(sock)
        in_buffer.write(packet)
        num -= len(packet)
    return in_buffer.getvalue()


class SocketClosed(Exception):

    @property
    def socket(self):
        return self.message


class StopRunning(BaseException):
    pass


class IRNetBoxProxy(object):

    MESSAGE_HEADER = struct.Struct(">cHB")
    RESPONSE_HEADER = struct.Struct(">HB")
    SEQUENCE_ID = struct.Struct(">H")
    MESSAGE_MARKER = "#"
    ASYNC_COMMAND = 0x30
    ASYNC_COMPLETE = 0x31
    ACK_NACK_INDEX = 3
    POWER_ON = 0x05
    POWER_OFF = 0x06
    IGNORED_COMMANDS = frozenset((POWER_ON, POWER_OFF))

    USIZE_MAX = 65535

    def __init__(self, irnet_address, irnet_port=10001,
                 listen_address="0.0.0.0", listen_port=10001,
                 verbosity=0):
        self.irnet_addr = (irnet_address, irnet_port)
        self.listen_addr = (listen_address, listen_port)
        self.verbosity = verbosity
        self.counter = itertools.count()
        self.async_commands = {}
        self.listen_sock = None
        self.irnet_sock = None
        self.read_sockets = {}

    def make_id(self):
        command_id = None
        while command_id is None or command_id in self.async_commands:
            command_id = self.counter.next()
        if command_id > self.USIZE_MAX:
            self.counter = itertools.count()
            return self.make_id()
        return command_id

    def replace_sequence_id(self, data, new_id):
        return self.SEQUENCE_ID.pack(new_id) + data[self.SEQUENCE_ID.size:]

    def get_message_from_irnet(self, expect_sync_response=True):
        header_data = safe_recv(self.irnet_sock, self.RESPONSE_HEADER.size)
        response_len, response_type = self.RESPONSE_HEADER.unpack(header_data)
        data = safe_recv(self.irnet_sock, response_len)
        if response_type == self.ASYNC_COMPLETE:
            self.handle_async_response(header_data, data)
            if expect_sync_response:
                return self.get_message_from_irnet(True)
            else:
                return
        elif response_type == self.ASYNC_COMMAND:
            new_id, = struct.unpack_from("<H", data)
            _, old_id = self.async_commands[new_id]
            data = self.replace_sequence_id(data, old_id)
            if not data[self.ACK_NACK_INDEX]:
                # The async command request failed, remove record
                del self.async_commands[new_id]
        return response_type, header_data, data

    def handle_async_response(self, header, data):
        try:
            new_id, = self.SEQUENCE_ID.unpack_from(data)
            if new_id not in self.async_commands:
                self.warn("Sequence ID not recognised: %r" % (new_id, ))
                return
            sock, old_id = self.async_commands[new_id]
            data = self.replace_sequence_id(data, old_id)
            sock.sendall(header + data)
        except Exception, e:  # pylint: disable=W0703
            self.error(e, "Error sending async complete command", fatal=False)
        if new_id in self.async_commands:
            del self.async_commands[new_id]

    def get_message_from_client(self, sock):
        header = safe_recv(sock, self.MESSAGE_HEADER.size)
        marker, message_len, message_type = self.MESSAGE_HEADER.unpack(header)
        if marker == "q":
            raise StopRunning()
        elif marker != self.MESSAGE_MARKER:
            raise ValueError("Invalid message from client")
        data = safe_recv(sock, message_len)
        if message_type == self.ASYNC_COMMAND:
            old_id, = self.SEQUENCE_ID.unpack_from(data)
            new_id = self.make_id()
            self.async_commands[new_id] = (sock, old_id)
            data = self.replace_sequence_id(data, new_id)
        return message_type, header, data

    def send_management_command(self, message_type):
        message = self.MESSAGE_HEADER.pack(self.MESSAGE_MARKER, 0, message_type)
        self.irnet_sock.sendall(message)
        response_type, _, _ = self.get_message_from_irnet(True)
        assert response_type == message_type

    def accept_client(self):
        new_client, (addr, _) = self.listen_sock.accept()
        self.info("Accepted connection from %s" % (addr,))
        # pylint: disable=E1101
        self.read_sockets[new_client.fileno()] = new_client

    def read_client_command(self, sock):
        try:
            message_type, header, message = self.get_message_from_client(sock)
            if message_type in self.IGNORED_COMMANDS:
                response_header = self.RESPONSE_HEADER.pack(0, message_type)
                response = ""
            else:
                self.irnet_sock.sendall(header + message)
                _, response_header, response = self.get_message_from_irnet(True)
            sock.sendall(response_header + response)
        except Exception, e:  # pylint: disable=W0703
            del self.read_sockets[sock.fileno()]
            sock.close()
            if isinstance(e, SocketClosed) and e.socket is sock:
                self.info("Client connection closed")
            else:
                self.error(e, "Error reading from client. Connection closed",
                           fatal=False)

    def info(self, data):
        if self.verbosity > 1:
            print data

    def warn(self, data):
        if self.verbosity > 0:
            sys.stderr.write("Warning: %s\n" % (data, ))

    def error(self, exception, data, fatal=True):
        if self.verbosity > 0:
            traceback.print_exc(exception)
        sys.stderr.write("%s\n" % (data, ))
        if fatal:
            sys.exit(1)

    def connect(self):
        try:
            self.listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.listen_sock.bind(self.listen_addr)
            self.listen_sock.listen(5)
        except Exception, e:  # pylint: disable=W0703
            self.error(e, "Could not bind to local address")

        try:
            self.irnet_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.irnet_sock.connect(self.irnet_addr)
        except Exception, e:  # pylint: disable=W0703
            self.error(e, "Could not connect to irNetBox.")
        self.read_sockets = {
            self.listen_sock.fileno(): self.listen_sock,
            self.irnet_sock.fileno(): self.irnet_sock
        }

    def run(self):
        self.connect()
        try:
            self.send_management_command(self.POWER_ON)
        except Exception, e:  # pylint: disable=W0703
            self.error(
                e, "Connected to irNetBox, but could not send power on command")

        self.info("Listening for connections on %s:%s" % self.listen_addr)
        try:
            while True:
                to_read = self.read_sockets.keys()
                ready_to_read, _, _ = select.select(to_read, [], [])
                for socket_fd in ready_to_read:
                    sock = self.read_sockets[socket_fd]
                    if sock is self.listen_sock:
                        self.accept_client()
                    elif sock is self.irnet_sock:
                        self.get_message_from_irnet(False)
                    else:
                        self.read_client_command(sock)
        finally:
            try:
                self.send_management_command(self.POWER_OFF)
            except Exception, e:  # pylint: disable=W0703
                self.error(e, "Could not turn irNetBox off", fatal=False)
            for sock in self.read_sockets.viewvalues():
                try:
                    sock.close()
                except:  # pylint: disable=W0702
                    pass


def parse_args(args=None):
    if args is None:
        args = sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('-i', '--listen-address', dest='listen_address',
                        help='IP address to listen on [%(default)s]',
                        default="0.0.0.0")
    parser.add_argument('-p', '--listen-port', type=int, dest='listen_port',
                        help='Port to listen on [%(default)s]', default=10001)
    parser.add_argument('-r', '--irnetbox-address', dest='irnet_address',
                        help='IRNetBox address', required=True)
    parser.add_argument('--irnetbox-port', dest='irnet_port',
                        help='IRNetBox port [%(default)s]', default=10001,
                        type=int)
    parser.add_argument('-v', '--verbosity', action="count",
                        help='Increase verbosity', default=0)

    options = parser.parse_args(args)
    options.error = parser.error
    return options


def main():
    options = parse_args()

    proxy = IRNetBoxProxy(irnet_address=options.irnet_address,
                          irnet_port=options.irnet_port,
                          listen_address=options.listen_address,
                          listen_port=options.listen_port,
                          verbosity=options.verbosity)
    try:
        proxy.run()
    except (KeyboardInterrupt, StopRunning), e:
        proxy.error(e, "Stopped")
    except Exception, e:
        proxy.error(e, "irNetProxy encountered an error")

if __name__ == "__main__":
    sys.exit(main())
