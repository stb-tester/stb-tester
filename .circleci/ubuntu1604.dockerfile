FROM ubuntu:16.04

RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && \
    apt-get install -y \
        ca-certificates \
        chromium-browser \
        curl \
        expect \
        expect-dev \
        gdb \
        gir1.2-gstreamer-1.0 \
        gir1.2-gudev-1.0 \
        git \
        gstreamer1.0-libav \
        gstreamer1.0-plugins-bad \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good \
        gstreamer1.0-tools \
        gstreamer1.0-x \
        gzip \
        language-pack-en \
        libgstreamer1.0-dev \
        libgstreamer-plugins-base1.0-dev \
        libopencv-dev \
        liborc-0.4-dev \
        librsvg2-bin \
        lighttpd \
        moreutils \
        pep8 \
        python-dev \
        python-docutils \
        python-flask \
        python-gi \
        python-jinja2 \
        python-kitchen \
        python-libcec \
        python-lxml \
        python-matplotlib \
        python-mock \
        python-nose \
        python-numpy \
        python-opencv \
        python-pip \
        python-pysnmp4 \
        python-qrcode \
        python-requests \
        python-scipy \
        python-serial \
        python-yaml \
        python-zbar \
        ratpoison \
        socat \
        ssh \
        sudo \
        tar \
        tesseract-ocr \
        tesseract-ocr-deu \
        tesseract-ocr-eng \
        time \
        v4l-utils \
        wget \
        xdotool \
        xserver-xorg-video-dummy \
        xterm && \
    apt-get clean

RUN pip install \
        astroid==1.4.8 \
        isort==3.9.0 \
        pylint==1.6.4 \
        pytest==3.3.1 \
        responses==0.5.1

# Ubuntu parallel package conflicts with moreutils, so we have to build it
# ourselves.
RUN mkdir -p /src && \
    cd /src && \
    { wget http://ftpmirror.gnu.org/parallel/parallel-20140522.tar.bz2 || \
      wget http://ftp.gnu.org/gnu/parallel/parallel-20140522.tar.bz2 || \
      exit 0; } && \
    tar -xvf parallel-20140522.tar.bz2 && \
    cd parallel-20140522/ && \
    ./configure --prefix=/usr/local && \
    make && \
    make install && \
    cd && \
    rm -rf /src && \
    mkdir -p $HOME/.parallel && \
    touch $HOME/.parallel/will-cite  # Silence citation warning
