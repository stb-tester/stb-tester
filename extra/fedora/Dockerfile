# Docker container running Fedora 20 for building & testing stb-tester RPMs on
# Fedora.

FROM mattdm/fedora:f20
MAINTAINER David Röthlisberger "david@rothlis.net"

RUN rpm -i http://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-20.noarch.rpm
RUN yum install -y copr-cli git rpm-build wget yum-utils
