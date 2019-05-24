# If you change this dockerfile, run `make publish-ci-docker-images`.

FROM ubuntu:18.04

RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && \
    apt-get install -y \
        ca-certificates \
        curl \
        expect \
        gdb \
        gir1.2-gstreamer-1.0 \
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
        moreutils \
        parallel \
        pep8 \
        pylint3 \
        python3-docutils \
        python3-flask \
        python3-future \
        python3-gi \
        python3-jinja2 \
        python3-lmdb \
        python3-lxml \
        python3-mock \
        python3-nose \
        python3-numpy \
        python3-opencv \
        python3-pip \
        python3-pysnmp4 \
        python3-pytest \
        python3-requests \
        python3-responses \
        python3-scipy \
        python3-serial \
        python3-yaml \
        socat \
        ssh \
        sudo \
        tar \
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

RUN ln -s python3.6 /usr/bin/python && \
    ln -s pylint3 /usr/bin/pylint && \
    ln -s pytest-3 /usr/bin/pytest && \
    ln -s py.test-3 /usr/bin/py.test
