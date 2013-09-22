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

Status
------

The VM will recognise any of the following devices connected to your host PC:

* Hauppauge HD PVR video-capture device
* RedRat3 USB infrared transceiver

To use the RedRat3 (or any other lirc-based infrared emitter) you still have to
provide a ``/etc/lirc/lircd.conf`` file describing your remote control; see
`"Configuring LIRC" <http://stb-tester.com/lirc.html>`_. If your infrared
hardware device is something other than ``/dev/lirc0`` then you'll also need to
edit ``REMOTE_DEVICE`` in ``/etc/lirc/hardware.conf``.
