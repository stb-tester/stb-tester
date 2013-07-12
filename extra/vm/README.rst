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
3. Run ``vagrant up`` from this directory.

Log in as the user ``vagrant``, password ``vagrant``. You can ssh to the VM
with ``vagrant ssh``.

Status
------

The redrat3 driver on Ubuntu 12.04 doesn't send infrared signals correctly. The
`RedRat website <http://www.redrat.co.uk/software/linux/RR-LIRC.html>`_
recommends the driver in kernel 3.3; Ubuntu 12.04 has kernel 3.2. This only
matters if you're using the RedRat3 infrared emitter; other supported emitters
(such as the RedRat irNetBox) work correctly.

You still have to install & configure ``lirc`` yourself. In particular, you'll
need to provide a ``lircd.conf`` file describing your remote control.

We use Ubuntu 12.04 (the "Long-Term Support" release, supported by Canonical
until April 2017) because vagrant hosts a base VM image (at
http://files.vagrantup.com/precise32.box). These images are quite large, so we
don't want to host them ourselves. You can upgrade to Ubuntu 12.10 (kernel 3.5)
with ``sudo do-release-upgrade -d``.

Ubuntu does host vagrant images for newer Ubuntu releases (at
http://cloud-images.ubuntu.com/vagrant/) but those images don't include the
redrat3 driver at all, nor the v4l2 drivers for devices such as the Hauppauge
HD PVR.
