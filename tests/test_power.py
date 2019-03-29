"""Tests for the _ATEN_PE6108G PDU class"""
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from future import standard_library
standard_library.install_aliases()
from builtins import *  # pylint:disable=redefined-builtin,unused-wildcard-import,wildcard-import,wrong-import-order
from contextlib import contextmanager

import pytest
from mock import patch
from pysnmp.proto.rfc1902 import Integer

from _stbt.power import uri_to_power_outlet


def mock_data(int_value):
    """Match the format of the data returned from pysnmp"""
    return (None, None, None, [(oid, Integer(int_value))])


@contextmanager
def mock_command_gen():
    """Perform mocks and return a mocked CommandGenerator instance."""
    with patch('time.sleep'),\
            patch('pysnmp.entity.rfc3413.oneliner.cmdgen.UdpTransportTarget'),\
            patch('pysnmp.entity.rfc3413.oneliner.cmdgen.CommandGenerator')\
            as mocked_command_gen:
        yield mocked_command_gen.return_value


outlet = 1
oid = "1.3.6.1.4.1.21317.1.3.2.2.2.2.{0}.0".format(outlet + 1)


def test_aten_get_on():
    with mock_command_gen() as mock_command:
        mock_command.getCmd.return_value = mock_data(2)
        aten = uri_to_power_outlet('aten:mock.host.name:1')

        result = aten.get()

        assert result is True


def test_aten_get_off():
    with mock_command_gen() as mock_command:
        mock_command.getCmd.return_value = mock_data(1)
        aten = uri_to_power_outlet('aten:mock.host.name:1')

        result = aten.get()

        assert result is False


def test_aten_set_on():
    with mock_command_gen() as mock_command:
        mock_command.setCmd.return_value = mock_data(2)
        mock_command.getCmd.side_effect = [mock_data(n) for n in (1, 1, 1, 2)]
        aten = uri_to_power_outlet('aten:mock.host.name:1')

        aten.set(True)

        assert mock_command.getCmd.call_count == 4


def test_aten_set_off():
    with mock_command_gen() as mock_command:
        mock_command.setCmd.return_value = mock_data(1)
        mock_command.getCmd.side_effect = [mock_data(n) for n in (2, 2, 1)]
        aten = uri_to_power_outlet('aten:mock.host.name:1')

        aten.set(False)

        assert mock_command.getCmd.call_count == 3


def test_aten_set_timeout():
    with mock_command_gen() as mock_command:
        mock_command.setCmd.return_value = mock_data(1)
        mock_command.getCmd.return_value = mock_data(2)
        aten = uri_to_power_outlet('aten:mock.host.name:1')

        with pytest.raises(RuntimeError):
            aten.set(False)
