# If you change this dockerfile, run `make publish-ci-docker-images`.

FROM ubuntu:22.04

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
        gstreamer1.0-plugins-ugly \
        gstreamer1.0-tools \
        gstreamer1.0-x \
        gzip \
        language-pack-en \
        librsvg2-bin \
        libxxhash0 \
        lirc \
        moreutils \
        parallel \
        pep8 \
        pylint \
        python3-cec \
        python3-docutils \
        python3-gi \
        python3-ipython \
        python3-jinja2 \
        python3-lmdb \
        python3-lxml \
        python3-networkx \
        python3-nose \
        python3-numpy \
        python3-opencv \
        python3-pip \
        python3-pysnmp4 \
        python3-pytest \
        python3-requests \
        python3-responses \
        python3-serial \
        python3-yaml \
        ssh \
        sudo \
        tar \
        tcl8.6 \
        tesseract-ocr \
        time \
        wget \
        xterm && \
    apt-get clean

RUN pip3 install pyright[nodejs] && pyright --version

RUN mkdir -p $HOME/.parallel && \
    touch $HOME/.parallel/will-cite  # Silence citation warning

# Tesseract data files for Legacy *and* LSTM engines.
ADD https://github.com/tesseract-ocr/tessdata/raw/590567f/deu.traineddata \
    https://github.com/tesseract-ocr/tessdata/raw/590567f/eng.traineddata \
    https://github.com/tesseract-ocr/tessdata/raw/590567f/osd.traineddata \
    https://github.com/tesseract-ocr/tessdata/raw/590567f/pol.traineddata \
    /usr/share/tesseract-ocr/4.00/tessdata/
