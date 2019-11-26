# If you change this dockerfile, run `make publish-ci-docker-images`.

FROM ubuntu:18.04

RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        expect \
        git \
        gzip \
        language-pack-en \
        librsvg2-bin \
        moreutils \
        parallel \
        pep8 \
        pylint3 \
        python3-docutils \
        python3-future \
        python3-jinja2 \
        python3-lmdb \
        python3-lxml \
        python3-mock \
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

RUN mkdir -p $HOME/.parallel && \
    touch $HOME/.parallel/will-cite  # Silence citation warning

# Tesseract data files for Legacy *and* LSTM engines.
ADD https://github.com/tesseract-ocr/tessdata/raw/590567f/deu.traineddata \
    https://github.com/tesseract-ocr/tessdata/raw/590567f/eng.traineddata \
    https://github.com/tesseract-ocr/tessdata/raw/590567f/osd.traineddata \
    /usr/share/tesseract-ocr/4.00/tessdata/
