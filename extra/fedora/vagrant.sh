#!/bin/bash

# Automated provisioning script run as the `root` user by `vagrant up`
# -- see `./Vagrantfile`.

set -e

apt-get update
apt-get install -y docker.io
usermod -a -G docker vagrant
service ufw stop &>/dev/null </dev/null || echo error stopping ufw firewall >&2
