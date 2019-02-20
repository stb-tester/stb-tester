# Docker container running Ubuntu 18.04 for building & testing stb-tester debs
# on Ubuntu.

FROM ubuntu:18.04
MAINTAINER David Röthlisberger "david@stb-tester.com"

# Build dependencies:
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
        build-essential devscripts @BUILDDEPENDS@

RUN adduser --gecos "" --disabled-password stb-tester && \
    mkdir /etc/sudoers.d && \
    echo "stb-tester	ALL=(ALL:ALL)	NOPASSWD:ALL" >/etc/sudoers.d/stb-tester && \
    chmod 0440 /etc/sudoers.d/stb-tester

USER stb-tester
ENV HOME /home/stb-tester
ENV LANG C.UTF-8
WORKDIR /home/stb-tester
