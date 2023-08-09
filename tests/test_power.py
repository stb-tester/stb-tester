"""Tests for the _ATEN_PE6108G PDU class"""

import configparser
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from pysnmp.proto.rfc1902 import Integer

from _stbt.power import config_to_power_outlet

CONFIG_INI = """
[device_under_test]
power_outlet = myaten

[power_outlet myaten]
type = aten
address = mock.host.name
outlet = 1
"""


CONFIG = configparser.ConfigParser()
CONFIG.read_string(CONFIG_INI)


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
        aten = config_to_power_outlet(config=CONFIG)

        result = aten.get()

        assert result is True


def test_aten_get_off():
    with mock_command_gen() as mock_command:
        mock_command.getCmd.return_value = mock_data(1)
        aten = config_to_power_outlet(config=CONFIG)

        result = aten.get()

        assert result is False


def test_aten_set_on():
    with mock_command_gen() as mock_command:
        mock_command.setCmd.return_value = mock_data(2)
        mock_command.getCmd.side_effect = [mock_data(n) for n in (1, 1, 1, 2)]
        aten = config_to_power_outlet(config=CONFIG)

        aten.set(True)

        assert mock_command.getCmd.call_count == 4


def test_aten_set_off():
    with mock_command_gen() as mock_command:
        mock_command.setCmd.return_value = mock_data(1)
        mock_command.getCmd.side_effect = [mock_data(n) for n in (2, 2, 1)]
        aten = config_to_power_outlet(config=CONFIG)

        aten.set(False)

        assert mock_command.getCmd.call_count == 3


def test_aten_set_timeout():
    with mock_command_gen() as mock_command:
        mock_command.setCmd.return_value = mock_data(1)
        mock_command.getCmd.return_value = mock_data(2)
        aten = config_to_power_outlet(config=CONFIG)

        with pytest.raises(RuntimeError):
            aten.set(False)


def test_nooutlet():
    p = configparser.ConfigParser()
    pdu = config_to_power_outlet(config=p)

    # If we've got no power control then we can't turn the power off:
    assert pdu.get()

    # No-op
    pdu.power_on()

    with pytest.raises(Exception):
        pdu.power_off()
