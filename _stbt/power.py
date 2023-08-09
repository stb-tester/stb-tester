from __future__ import annotations

import enum
import errno
import json
import re
import subprocess
import time
import typing

from _stbt.config import ConfigurationError
from _stbt.types import PDU

if typing.TYPE_CHECKING:
    # pylint: disable=unused-import
    import configparser
    import pysnmp.hlapi
    SnmpAuth: typing.TypeAlias = (
        pysnmp.hlapi.CommunityData | pysnmp.hlapi.UsmUserData)
    # pylint: enable=unused-import


def uri_to_power_outlet(uri: str) -> PDU:
    remotes = [
        (r'none', _NoOutlet),
        (r'file:(?P<filename>[^:]+)', _FileOutlet),
        (r'aten:(?P<address>[^: ]+):(?P<outlet>[^: ]+)',
         _ATEN_PE6108G.from_uri_groups),
        (r'rittal:(?P<address>[^: ]+):(?P<outlet>[^: ]+)'
         ':(?P<community>[^: ]+)', _RittalSnmpPower.from_uri_groups),
        (r'aviosys-8800-pro(:(?P<filename>[^:]+))?', _new_aviosys_8800_pro),
        (r'kasa:(?P<hostname>[^:]+)', Kasa),
    ]
    for regex, factory in remotes:
        m = re.match(regex, uri, re.VERBOSE | re.IGNORECASE)
        if m:
            return factory(**m.groupdict())
    raise ConfigurationError('Invalid power outlet URI: "%s"' % uri)


def config_to_power_outlet(
        power_outlet: "str | None" = None,
        config: "dict[str, dict[str, str]] | configparser.ConfigParser | None" = None  # pylint: disable=line-too-long
) -> PDU:
    """
    Factory function for PDU objects based on stbt config.
    `device_under_test.power_outlet` references a section in the config file.
    The section contains keys and values to configure the PDU.  Example:

    ```
    [device_under_test]
    power_outlet = myoutlet

    [power_outlet myoutlet]
    type = apc7xxx
    address = 192.168.7.5
    outlet = 1
    ```

    `type` is mandatory, other keys depend on the type of PDU.  Common keys are:

    * `address`: IP address or hostname of the PDU
    * `outlet`: Outlet number

    In addition to the above, `rittal` PDUs require a `community` key.

    The `device_under_test.power_outlet` key may also specify a URI as accepted
    by `uri_to_power_outlet` for backwards compatible with old config files.
    This may be removed in the future once no customers are using it.
    """
    if config is None:
        from _stbt.config import _config_init
        config = _config_init()
    if power_outlet is not None:
        pduname = power_outlet
    else:
        try:
            pduname = config["device_under_test"]["power_outlet"]
        except KeyError:
            return _NoOutlet()
    try:
        # For backwards compatibility with old config files
        return uri_to_power_outlet(pduname)
    except ConfigurationError:
        pass
    try:
        section = config["power_outlet %s" % pduname]
    except KeyError:
        raise ConfigurationError(
            "Expected to find section [power_outlet %s] in config file because "
            "device_under_test.power_outlet == %r.  No such section found" %
            (pduname, pduname))
    try:
        ty = section["type"].lower()
        if ty == "none":
            return _NoOutlet()
        elif ty == "file":
            return _FileOutlet(section["filename"])
        elif ty == "aten":
            return _ATEN_PE6108G.from_config_section(section)
        elif ty == "apc":
            return _APC7xxx.from_config_section(section)
        elif ty == "rittal":
            return _RittalSnmpPower.from_config_section(section)
        elif ty == "aviosys-8800-pro":
            return _new_aviosys_8800_pro(section.get("filename"))
        elif ty == "kasa":
            return Kasa(section["address"])
        else:
            raise ConfigurationError(
                '%s: Unknown power outlet type: "%s"' % (pduname, ty))
    except KeyError as e:
        raise ConfigurationError(
            'Failed to find key "%s" in section [power_outlet %s] in config '
            'file' % (e.args[0], pduname))


class _NoOutlet(PDU):
    def set(self, power):
        if not power:
            raise RuntimeError(
                "Cannot disable power: no power outlet configured")

    def get(self):
        # If we can't turn it off, it must be on
        return True


class _FileOutlet(PDU):
    """Power outlet useful for testing"""
    def __init__(self, filename):
        self.filename = filename

    def set(self, power):
        with open(self.filename, 'wb') as f:
            f.write([b'0', b'1'][power])

    def get(self):
        try:
            with open(self.filename, 'rb') as f:
                return bool(int(f.read(1)))
        except IOError as e:
            if e.errno == errno.ENOENT:
                return True
            else:
                raise


class _Aviosys8800Pro(PDU):
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


def _new_aviosys_8800_pro(filename=None):
    import serial
    if filename is None:
        filename = '/dev/ttyACM0'
    return _Aviosys8800Pro(serial.Serial(filename, baudrate=19200))


class _FakeAviosys8800ProSerial():
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


class _RittalSnmpPower(PDU):
    """
    Tested with the DK 7955.310.  SNMP OIDs may be different on other devices.
    """
    def __init__(self, address: tuple[str, int], outlet: int,
                 snmp_auth: "SnmpAuth"):
        outlet = int(outlet)
        index = outlet - 1
        if index < 0:
            raise ValueError("Invalid outlet_no %i.  Min outlet no is 1" %
                             outlet)
        self._snmp = _SnmpInteger(
            address, "1.3.6.1.4.1.2606.7.4.2.2.1.11.1.%i" % (52 + index * 7),
            snmp_auth)

    @classmethod
    def from_uri_groups(cls, address, outlet, community):
        return cls.from_config_section({
            "address": address,
            "community": community,
            "outlet": outlet,
        })

    @classmethod
    def from_config_section(cls, section: dict[str, str]):
        address, auth = _snmp_config(section)
        return cls(address, int(section["outlet"]), auth)

    def get(self):
        return bool(self._snmp.get())

    def set(self, power):
        if self._snmp.set(int(bool(power))) != int(bool(power)):
            raise RuntimeError("Setting power failed with unknown error")


class _ATEN_PE6108G(PDU):
    """Class to control the ATEN PDU using pysnmp module. """
    AUTH_DEFAULTS = {"version": "2c", "community": "administrator"}

    def __init__(
            self, address: tuple[str, int], outlet: int, snmp_auth: "SnmpAuth"):
        outlet = int(outlet)
        outlet_offset = 1 if outlet <= 8 else 2
        self._snmp = _SnmpInteger(
            address, "1.3.6.1.4.1.21317.1.3.2.2.2.2.%i.0" % (
                outlet + outlet_offset), auth=snmp_auth)

    @classmethod
    def from_uri_groups(cls, address, outlet):
        return cls.from_config_section({"address": address, "outlet": outlet})

    @classmethod
    def from_config_section(cls, config: "dict[str, str]"):
        address, auth = _snmp_config(config, cls.AUTH_DEFAULTS)
        return cls(address, int(config['outlet']), auth)

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


class _APC7xxx(PDU):
    """Class to control the APC 7xxx PDU using pysnmp module. """
    PORT_STATE_CONTROL_OID = "1.3.6.1.4.1.318.1.1.12.3.3.1.1.4.{outlet}"

    class Cmd(enum.IntEnum):
        """See rPDUOutletControlOutletCommand in powernet446.mib:
        https://www.apc.com/us/en/download/document/APC_POWERNETMIB_446_EN/
        """
        IMMEDIATE_ON = 1
        IMMEDIATE_OFF = 2
        IMMEDIATE_REBOOT = 3
        OUTLET_UNKNOWN = 4
        DELAYED_ON = 5
        DELAYED_OFF = 6
        DELAYED_REBOOT = 7
        CANCEL_PENDING_COMMAND = 8

    def __init__(self, address: tuple[str, int], outlet: int, auth: SnmpAuth):
        outlet = int(outlet)
        self._snmp = _SnmpInteger(
            address, self.PORT_STATE_CONTROL_OID.format(outlet=outlet), auth)

    @classmethod
    def from_config_section(cls, section: dict[str, str]):
        address, auth = _snmp_config(section)
        return cls(address, int(section["outlet"]), auth)

    def set(self, power: bool):
        desired = int(
            self.Cmd.IMMEDIATE_ON if power else self.Cmd.IMMEDIATE_OFF)
        new_state = self._snmp.set(desired)
        if new_state != desired:
            raise RuntimeError(
                "Setting power failed: Got %s" % self.Cmd(new_state))

    def get(self):
        result = self.Cmd(self._snmp.get())
        if result not in [self.Cmd.IMMEDIATE_ON, self.Cmd.IMMEDIATE_OFF]:
            raise RuntimeError(
                "Getting power failed: Got %s" % result)
        return bool(result == self.Cmd.IMMEDIATE_ON)


# Sentinel:
class _NotSpecified:
    pass


def _snmp_config(
        section: "dict[str, str]",
        defaults: "dict[str, str] | None" = None
) -> "tuple[tuple[str, int], SnmpAuth]":
    """Convert a config section to a pysnmp auth data object.  This roughly
    expects the same keys and values as `man snmp.conf`, but snake_case rather
    than camelCase.
    """
    from pysnmp import hlapi

    if defaults is None:
        defaults = {}

    address = section["address"]
    if ':' in address:
        address, port = address.split(":", 2)
    else:
        port = "161"
    port = int(port)

    # Determine SNMP version automatically based on the authentication
    # options present:
    version = section.get("version")
    if version is None:
        if section.get("username"):
            version = "3"
        elif section.get("community"):
            version = "2c"
        elif "version" in defaults:
            version = defaults["version"]
        else:
            raise ConfigurationError(
                "No SNMP version specified and no authentication credentials "
                "provided")

    def get(key, default: "typing.Any" = _NotSpecified):
        out = section.get(key, defaults.get(key, default))
        if out is _NotSpecified:
            raise ConfigurationError("No %s specified" % key)
        return out

    if version == "3":
        # Configuration strings match `man snmpcmd`:
        kwargs = {}
        AUTH_PROTOS = {
            "MD5": hlapi.usmHMACMD5AuthProtocol,
            "SHA": hlapi.usmHMACSHAAuthProtocol,
            "SHA-224": hlapi.usmHMAC128SHA224AuthProtocol,
            "SHA-256": hlapi.usmHMAC192SHA256AuthProtocol,
            "SHA-384": hlapi.usmHMAC256SHA384AuthProtocol,
            "SHA-512": hlapi.usmHMAC384SHA512AuthProtocol,
        }
        auth_passphrase = get("auth_passphrase", None)
        auth_protocol = get("auth_protocol", None)
        if auth_passphrase and not auth_protocol:
            auth_protocol = "MD5"
        if auth_protocol:
            kwargs["authProtocol"] = AUTH_PROTOS[auth_protocol.upper()]
            kwargs["authKey"] = auth_passphrase

        PRIV_PROTOS = {
            "DES": hlapi.usmDESPrivProtocol,
            "AES": hlapi.usmAesCfb128Protocol,
        }
        priv_passphrase = get("priv_passphrase", None)
        priv_protocol = get("priv_protocol", None)
        if priv_passphrase and not priv_protocol:
            priv_protocol = "DES"
        if priv_protocol:
            kwargs["privProtocol"] = PRIV_PROTOS[priv_protocol.upper()]
            kwargs["privKey"] = priv_passphrase

        auth = hlapi.UsmUserData(userName=get("username"), **kwargs)
    elif version == "2c":
        auth = hlapi.CommunityData(get("community"), mpModel=1)
    elif version == "1":
        auth = hlapi.CommunityData(get("community"), mpModel=0)
    else:
        raise ValueError("Invalid SNMP version %s" % version)

    return ((address, port), auth)


def test_snmp_config():
    import pytest
    from pysnmp import hlapi

    with pytest.raises(KeyError):
        # address is mandatory
        _snmp_config({"community": "public"})

    with pytest.raises(ConfigurationError):
        # Some authentication credentials are required:
        _snmp_config({"address": "localhost"})

    # Can specifty a port:
    a, c = _snmp_config({"address": "localhost:1234", "community": "public"})
    assert a == ("localhost", 1234)

    a, c = _snmp_config({"address": "localhost", "community": "public"})
    assert a == ("localhost", 161)
    assert isinstance(c, hlapi.CommunityData)
    assert c.communityName == "public"

    # If community is specified, version defaults to 2c:
    assert c.mpModel == 1

    # But it can be overridden:
    _, c = _snmp_config({
        "address": "localhost", "community": "public", "version": "1"})
    assert c.mpModel == 0

    # Version 3 takes precedence over v2c if both are username and community
    # are specified:
    _, c = _snmp_config({
        "address": "localhost", "community": "public", "username": "stbt"})
    assert isinstance(c, hlapi.UsmUserData)
    assert c.userName == "stbt"
    assert c.authKey is None
    assert c.authProtocol == hlapi.usmNoAuthProtocol
    assert c.privKey is None
    assert c.privProtocol == hlapi.usmNoPrivProtocol

    _, c = _snmp_config({
        "address": "localhost", "username": "stbt",
        "auth_passphrase": "passw0rd!"})
    assert c.authKey == "passw0rd!"
    assert c.authProtocol == hlapi.usmHMACMD5AuthProtocol
    assert c.privKey is None

    _, c = _snmp_config({
        "address": "localhost", "username": "stbt",
        "auth_passphrase": "passw0rd!",
        "priv_passphrase": "s3cret"})
    assert c.privKey == "s3cret"
    assert c.privProtocol == hlapi.usmDESPrivProtocol

    _, c = _snmp_config({
        "address": "localhost", "username": "stbt",
        "auth_passphrase": "passw0rd!",
        "priv_passphrase": "s3cret",
        "auth_protocol": "sha",
        "priv_protocol": "aes"
    })
    assert c.authProtocol == hlapi.usmHMACSHAAuthProtocol
    assert c.privProtocol == hlapi.usmAesCfb128Protocol


class _SnmpInteger():
    def __init__(self, address: "tuple[str, int]", oid: str, auth: "SnmpAuth"):
        from pysnmp.entity.rfc3413.oneliner.cmdgen import UdpTransportTarget
        self.oid = oid
        self._transport = UdpTransportTarget(address)
        self._auth = auth

    def set(self, value: int) -> int:
        return self._cmd(value)

    def get(self) -> int:
        return self._cmd(None)

    def _cmd(self, value: "int | None") -> int:
        from pysnmp.entity.rfc3413.oneliner import cmdgen
        from pysnmp.proto.rfc1905 import NoSuchObject
        from pysnmp.proto.rfc1902 import Integer

        command_generator = cmdgen.CommandGenerator()

        if value is None:  # `status` command
            error_ind, _, _, var_binds = command_generator.getCmd(
                self._auth, self._transport, self.oid)
        else:
            error_ind, _, _, var_binds = command_generator.setCmd(
                self._auth, self._transport, (self.oid, Integer(value)))

        if error_ind is not None:
            raise RuntimeError("SNMP Error ({})".format(error_ind))

        _, result = var_binds[0]

        if isinstance(result, NoSuchObject):
            raise RuntimeError("No such outlet")

        if not isinstance(result, Integer):
            raise RuntimeError("Unexpected result ({})".format(result))

        return int(result)


class Kasa(PDU):
    """TP-Link Kasa smart plugs."""

    def __init__(self, hostname):
        self.hostname = hostname

    def set(self, power):
        # `kasa` CLI from python-kasa.
        subprocess.check_call(
            ["kasa", "--host", self.hostname, "--type", "plug",
             "on" if power else "off"])

    def get(self):
        json_data = subprocess.check_output(
            ["kasa", "--host", self.hostname, "--type", "plug", "--json",
             "state"])
        return _kasa_output_to_state(json.loads(json_data))


def _kasa_output_to_state(json_data):
    return bool(json_data["system"]["get_sysinfo"]["relay_state"])


def test_kasa_output_to_state():
    KASA_OUTPUT = {
        "system": {
            "get_sysinfo": {
                "sw_ver": "1.0.20 Build 221125 Rel.092759",
                "hw_ver": "1.0",
                "model": "KP115(UK)",
                "deviceId": "80063DA95EAC2AA16EB1ACED077C10E820CF1A73",
                "oemId": "C7A36E0C2D4BAB44DED6EF0870AC707F",
                "hwId": "39E8408ED974DD69D8A77D9F8781637E",
                "rssi": -10,
                "latitude_i": 514771,
                "longitude_i": -911,
                "alias": "Kasa CI PDU",
                "status": "new",
                "obd_src": "tplink",
                "mic_type": "IOT.SMARTPLUGSWITCH",
                "feature": "TIM:ENE",
                "mac": "9C:53:22:2B:55:38",
                "updating": 0,
                "led_off": 0,
                "relay_state": 1,
                "on_time": 3,
                "icon_hash": "",
                "dev_name": "Smart Wi-Fi Plug Mini",
                "active_mode": "none",
                "next_action": {
                    "type": -1
                },
                "ntc_state": 0,
                "err_code": 0
            }
        },
        "schedule": {
            "get_rules": {
                "rule_list": [],
                "version": 2,
                "enable": 0,
                "err_code": 0
            },
            "get_next_action": {
                "type": -1,
                "err_code": 0
            },
            "get_realtime": {
                "err_code": -2,
                "err_msg": "member not support"
            },
            "get_daystat": {
                "day_list": [
                    {
                        "year": 2023,
                        "month": 7,
                        "day": 19,
                        "time": 31
                    }
                ],
                "err_code": 0
            },
            "get_monthstat": {
                "month_list": [
                    {
                        "year": 2023,
                        "month": 7,
                        "time": 31
                    }
                ],
                "err_code": 0
            }
        },
        "anti_theft": {
            "get_rules": {
                "rule_list": [],
                "version": 2,
                "enable": 0,
                "err_code": 0
            },
            "get_next_action": {
                "err_code": -2,
                "err_msg": "member not support"
            }
        },
        "time": {
            "get_time": {
                "year": 2023,
                "month": 7,
                "mday": 19,
                "hour": 14,
                "min": 48,
                "sec": 36,
                "err_code": 0
            },
            "get_timezone": {
                "index": 39,
                "err_code": 0
            }
        },
        "cnCloud": {
            "get_info": {
                "username": "stb-tester@example.com",
                "server": "n-devs.tplinkcloud.com",
                "binded": 1,
                "cld_connection": 1,
                "illegalType": 0,
                "stopConnect": 0,
                "tcspStatus": 1,
                "fwDlPage": "",
                "tcspInfo": "",
                "fwNotifyType": -1,
                "err_code": 0
            }
        },
        "emeter": {
            "get_realtime": {
                "current_ma": 0,
                "voltage_mv": 242535,
                "power_mw": 0,
                "total_wh": 0,
                "err_code": 0
            },
            "get_daystat": {
                "day_list": [
                    {
                        "year": 2023,
                        "month": 7,
                        "day": 19,
                        "energy_wh": 0
                    }
                ],
                "err_code": 0
            },
            "get_monthstat": {
                "month_list": [
                    {
                        "year": 2023,
                        "month": 7,
                        "energy_wh": 0
                    }
                ],
                "err_code": 0
            }
        }
    }
    assert _kasa_output_to_state(KASA_OUTPUT) is True
