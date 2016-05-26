class HdmiCecControl(object):
    def __init__(self, device):
        import cec
        raise NotImplementedError()

    def press(self, key):
        import cec
        raise NotImplementedError()


def test_hdmi_cec_control():
    from .control import uri_to_remote
    control = uri_to_remote('hdmi-cec:192.168.1.3')
    assert False, "Tests not written"

controls = [
    (r'hdmi-cec:(?P<device>[^:]+)', HdmiCecControl),
]
