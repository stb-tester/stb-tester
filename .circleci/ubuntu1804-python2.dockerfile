# If you change this dockerfile, run `make publish-ci-docker-images`.

FROM ubuntu:18.04

RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        expect \
        gir1.2-gstreamer-1.0 \
        git \
        gstreamer1.0-libav \
        gstreamer1.0-plugins-bad \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good \
        gstreamer1.0-tools \
        gstreamer1.0-x \
        gzip \
        language-pack-en \
        librsvg2-bin \
        lirc \
        moreutils \
        parallel \
        pylint \
        python-docutils \
        python-flask \
        python-future \
        python-gi \
        python-jinja2 \
        python-kitchen \
        python-libcec \
        python-lmdb \
        python-lxml \
        python-mock \
        python-nose \
        python-numpy \
        python-opencv \
        python-pip \
        python-pysnmp4 \
        python-pytest \
        python-requests \
        python-responses \
        python-scipy \
        python-serial \
        python-yaml \
        socat \
        ssh \
        sudo \
        tar \
        tcl8.6 \
        tesseract-ocr \
        time \
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

# Work around python-libcec packaging bug
# https://bugs.launchpad.net/ubuntu/+source/libcec/+bug/1822066
RUN mv /usr/lib/python2.7.15rc1/dist-packages/cec /usr/lib/python2.7/dist-packages/
