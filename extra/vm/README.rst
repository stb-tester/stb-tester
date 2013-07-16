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

You still have to install & configure ``lirc`` yourself. In particular, you'll
need to provide a ``lircd.conf`` file describing your remote control.
