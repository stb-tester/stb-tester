import mock
#import socket
import unittest

import irnetproxy


def fake_recv(data):
    # Ugly hack to work around python scoping rules
    data = [bytes(data)]

    def recv(num):
        bytes_to_send = min(num, 5)
        to_send = data[0][:bytes_to_send]
        data[0] = data[0][bytes_to_send:]
        return to_send
    return recv


class ProxyTest(unittest.TestCase):

    def setUp(self):
        self.socket = mock.Mock()
        self.socket_patcher = mock.patch('socket.socket',
                                         return_value=self.socket)
        self.my_socket = self.socket_patcher.start()

    def tearDown(self):
        mock.patch.stopall()

    def test_id_generation(self):
        proxy = irnetproxy.IRNetBoxProxy("no_address")
        for i in range(65536):
            self.assertEqual(proxy.make_id(), i)
        self.assertEqual(proxy.make_id(), 0)

    def test_id_generation_skips_active_ids(self):
        proxy = irnetproxy.IRNetBoxProxy("no_address")
        proxy.async_commands[2] = None

        self.assertEqual(proxy.make_id(), 0)
        self.assertEqual(proxy.make_id(), 1)
        self.assertEqual(proxy.make_id(), 3)

    def test_replace_sequence(self):
        proxy = irnetproxy.IRNetBoxProxy("no_address")
        data = "YYYY"
        self.assertEqual(proxy.replace_sequence_id(data, 1), "\x00\x01YY")
        self.assertEqual(proxy.replace_sequence_id(data, 65535), "\xff\xffYY")

    def test_safe_recv(self):
        def recv(x):
            self.assertNotEqual(x, 0)
            return "0" if x == 1 else ("0" * (x / 2))
        sock = mock.Mock(recv=recv)
        self.assertEqual(irnetproxy.safe_recv(sock, 100), "0" * 100)

    def test_get_message_from_irnet(self):
        proxy = irnetproxy.IRNetBoxProxy("no_address")
        DATA_LENGTH = "\x00\x02"
        MESSAGE_TYPE = "\x04"
        self.socket.recv = fake_recv(DATA_LENGTH + MESSAGE_TYPE + "HI")

        proxy.connect()
        message_type, _, data = proxy.get_message_from_irnet()
        self.assertEqual(message_type, 4)
        self.assertEqual(data, "HI")


if __name__ == "__main__":
    unittest.main()
