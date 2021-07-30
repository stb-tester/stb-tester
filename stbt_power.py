#!/usr/bin/python3

import argparse
import sys
from textwrap import dedent

from _stbt.config import get_config
from _stbt.power import uri_to_power_outlet


def main(argv):
    parser = argparse.ArgumentParser(
        description="Control and query a computer controllable power outlet",
        formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument(
        "--power-outlet", metavar="URI",
        default=get_config("global", "power_outlet", ""), help=dedent("""\
             Address of the power device and the outlet on the device.
             The format of <uri> is either:
               aten:<hostname>:<outlet> - For ATEN network controlled PDU
               ipp:<hostname>:<outlet> - For IP Power 9258 network controlled PDU
               pdu:<hostname>:<outlet> - For PDUeX KWX network controlled PDU
               rittal:<hostname>:<outlet>:<community> - For Rittal 7955.310 network controlled PDU
               aviosys-8800-pro[:<serial device>] - For Aviosys 8800 Pro USB
                   controlled outlets
             where
               <hostname>       The device's network address.
               <outlet>         Address of the individual power outlet on
                                the device. Allowed values depend on the
                                specific device model.
               <serial device>  The device name of the serial device that the
                                8800 Pro exposes.  Defaults to /dev/ttyACM0
             This URI defaults to from stbt.conf's "global.power_outlet" if not
             specified on the command line.
             """))

    parser.add_argument(
        "command", choices=["on", "off", "status"], metavar="command",
        help=dedent("""\
            on|off:  Turn power on or off
            status:  Prints ON if the outlet is powered, otherwise prints OFF
            """))
    args = parser.parse_args(argv[1:])

    outlet = uri_to_power_outlet(args.power_outlet)

    if args.command == "on":
        outlet.set(True)
    elif args.command == "off":
        outlet.set(False)
    elif args.command == "status":
        sys.stdout.write("ON\n" if outlet.get() else "OFF\n")
    else:
        assert False

if __name__ == '__main__':
    sys.exit(main(sys.argv))
