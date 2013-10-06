VirtualBox VM for stb-tester
============================

The ``Vagrantfile`` in this directory is a configuration script that will
provision a Virtual Machine running Ubuntu with stb-tester and all its
dependencies installed. This uses `vagrant <http://www.vagrantup.com>`_, a tool
for provisioning virtual machines.

Instructions
------------

1. `Install vagrant <http://docs.vagrantup.com/v2/installation/index.html>`_
2. `Install VirtualBox <https://www.virtualbox.org/wiki/Downloads>`_
3. Run ``vagrant up`` from this directory. When it finishes, run ``vagrant
   reload`` to reboot the VM (because the initial ``vagrant up`` installed
   a newer kernel).

Log in as the user ``vagrant``, password ``vagrant``. You can ssh to the VM
with ``vagrant ssh``.

Hardware
--------

The VM will recognise any of the following devices connected to your host PC:

* Hauppauge HD PVR video-capture device
* RedRat3 USB infrared transceiver

To use the RedRat3 (or any other lirc-based infrared emitter) you still have to
provide a ``/etc/lirc/lircd.conf`` file describing your remote control; see
`"Configuring LIRC" <http://stb-tester.com/lirc.html>`_. If your infrared
hardware device is something other than ``/dev/lirc0`` then you'll also need to
edit ``REMOTE_DEVICE`` in ``/etc/lirc/hardware.conf``.

VidiU
-----

The `Teradek VidiU <http://www.teradek.com/pages/vidiu>`_ is a video-capture
hardware device that takes HDMI input and outputs RTMP (Flash video) over
ethernet or WiFi. The VidiU acts as an RTMP client, so it needs an RTMP server
to publish to.

Configure the VidiU through its web interface (point your browser to the
VidiU's IP address, which you can find using the device's physical
joysticks by navigating to `Network settings` -> `Wired` -> `Info
menu`):

- Broadcast settings - Mode: Manual
- Broadcast settings - RTMP server URL: rtmp://<address>/live
- Broadcast settings - Stream name: <stream name>
- Broadcast settings - User agent: Teradek
- Broadcast settings - Username: <blank>
- Broadcast settings - Password: <blank>
- Broadcast settings - Auto start: On
- Broadcast settings - Auto reconnect: On

After configuring the VidiU, it should automatically establish a
connection to the RTMP server. Once connected, it will show the status
LIVE in the top-right corner.

crtmpserver is an open-source RTMP server with packages already
available in the Ubuntu repositories. The `crtmpserver.lua`
configuration added here is not very secure, as it allows any client to
push streams to the server. The logs are at
/var/log/crtmpserver/main.log.

Configure stb-tester as an RTMP client that reads from the crtmpserver,
with a source pipeline like::

  rtmpsrc location=rtmp://localhost/live/<stream name>\ live=1 ! decodebin2

Note the backslash after the stream name -- "live=1" is part of the "location"
value, not a separate "live" GStreamer property.
