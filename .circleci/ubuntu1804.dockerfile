# If you change this dockerfile, run `make publish-ci-docker-images`.

FROM ubuntu:18.04

RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && \
    apt-get install -y \
        ca-certificates \
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
        gzip \
        language-pack-en \
        libgstreamer1.0-dev \
        libgstreamer-plugins-base1.0-dev \
        libopencv-dev \
        liborc-0.4-dev \
        librsvg2-bin \
        lighttpd \
        moreutils \
        parallel \
        pep8 \
        pylint \
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
        python-pytest \
        python-qrcode \
        python-requests \
        python-responses \
        python-scipy \
        python-serial \
        python-yaml \
        python-zbar \
        socat \
        ssh \
        sudo \
        tar \
        tesseract-ocr \
        time \
        v4l-utils \
        wget \
        xterm && \
    apt-get clean

RUN mkdir -p $HOME/.parallel && \
    touch $HOME/.parallel/will-cite  # Silence citation warning

# Tesseract data files for Legacy *and* LSTM engines.
ADD https://github.com/tesseract-ocr/tessdata/raw/590567f/deu.traineddata \
    https://github.com/tesseract-ocr/tessdata/raw/590567f/eng.traineddata \
    https://github.com/tesseract-ocr/tessdata/raw/590567f/osd.traineddata \
    /usr/share/tesseract-ocr/4.00/tessdata/
