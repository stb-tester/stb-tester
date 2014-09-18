FROM ubuntu:14.04
MAINTAINER will@stb-tester.com

ENV DEBIAN_FRONTEND noninteractive

ADD extra/debian/control /tmp/runtime-deps
RUN apt-get update && \
    apt-get dist-upgrade -y && \
    apt-get install -y $(awk '/^         [^$ ]/ {print $1}' /tmp/runtime-deps | sed 's/,//g') && \
    apt-get clean && \
    rm /tmp/runtime-deps

ADD . /tmp/source
RUN apt-get install -y git make python-docutils && \
    make -C /tmp/source prefix=/usr sysconfdir=/etc libexecdir=/usr/lib install && \
    rm -Rf /tmp/source && \
    apt-get remove -y --purge git make python-docutils && \
    apt-get -y --purge autoremove && \
    apt-get clean

RUN adduser --home /var/lib/stbt --uid 1000 stb-tester && \
    echo "stb-tester    ALL=(ALL:ALL) NOPASSWD:ALL" >/etc/sudoers.d/stb-tester
    
USER stb-tester

RUN mkdir -p /var/lib/stbt/results /var/lib/stbt/tests

VOLUME ["/var/lib/stbt/results"]

ENTRYPOINT ["/usr/bin/stbt"]
