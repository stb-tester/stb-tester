# Docker container running Fedora 20 for building & testing stb-tester RPMs on
# Fedora.

FROM fedora:20
MAINTAINER David Röthlisberger "david@rothlis.net"

RUN rpm -i http://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-20.noarch.rpm

RUN adduser stb-tester && \
    echo  "stb-tester	ALL=(ALL)	NOPASSWD: ALL" >>/etc/sudoers && \
    sed -i 's/Defaults.*requiretty//' /etc/sudoers

USER stb-tester
ENV HOME /home/stb-tester
WORKDIR /home/stb-tester
ENTRYPOINT ["/bin/bash", "-c"]

RUN mkdir rpmbuild
