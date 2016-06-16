from .logging import debug


class HdmiCecError(Exception):
    pass


class HdmiCecControl(object):

    # Map our recommended keynames (from linux input-event-codes.h) to the
    # equivalent CEC commands.
    # The mapping between CEC commands and code can be found at http://www.cec-o-matic.com
    # or in HDMI-CEC specification 1.3a
    _KEYNAMES = {
        "KEY_OK": "14:44:00",
        "KEY_UP": "14:44:01",
        "KEY_DOWN": "14:44:02",
        "KEY_LEFT": "14:44:03",
        "KEY_RIGHT": "14:44:04",
        "KEY_BACK": "14:44:0D"
    }

    def __init__(self, device):
        import cec
        self.cecconfig = cec.libcec_configuration()
        self.cecconfig.strDeviceName = "STB-Tester"
        self.cecconfig.bActivateSource = 0
        self.cecconfig.deviceTypes.Add(cec.CEC_DEVICE_TYPE_RECORDING_DEVICE)
        self.cecconfig.clientVersion = cec.LIBCEC_VERSION_CURRENT
        self.lib = cec.ICECAdapter.Create(self.cecconfig)
        # print libCEC version and compilation information
        debug("libCEC version " + self.lib.VersionToString(self.cecconfig.serverVersion) +
              " loaded: " + self.lib.GetLibInfo())

        if device is None:
            device = self.detect_adapter()
            if device is None:
                raise HdmiCecError("No adapter found")
        if self.lib.Open(device):
            debug("Connection to CEC adapter opened")
        else:
            raise HdmiCecError("Failed to open a connection to the CEC adapter")

    def press(self, key):
        cec_command = self._KEYNAMES.get(key)
        cmd = self.lib.CommandFromString(cec_command)
        debug("Transmit " + key + " as " + cec_command)
        if self.lib.Transmit(cmd):
            self.lib.Transmit(self.lib.CommandFromString('14:45'))
            debug("Command sent")
        else:
            raise HdmiCecError("Failed to send command")

    # detect an adapter and return the com port path
    def detect_adapter(self):
        retval = None
        adapters = self.lib.DetectAdapters()
        for adapter in adapters:
            debug("Found a CEC adapter:")
            debug("Port:     " + adapter.strComName)
            debug("Vendor:   " + hex(adapter.iVendorId))
            debug("Product:  " + hex(adapter.iProductId))
            retval = adapter.strComName
        return retval


def test_hdmi_cec_control():
    # from .control import uri_to_remote
    # control = uri_to_remote('hdmi-cec:192.168.1.3')
    assert False, "Tests not written"

controls = [
    (r'hdmi-cec:(?P<device>[^:]+)', HdmiCecControl),
]
