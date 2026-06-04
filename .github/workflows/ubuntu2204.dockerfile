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
        libcairo2-dev \
        libgirepository1.0-dev \
        librsvg2-bin \
        lirc \
        moreutils \
        parallel \
        python3-cec \
        python3-dev \
        python3-pip \
        ssh \
        sudo \
        tar \
        tcl8.6 \
        tesseract-ocr \
        time \
        wget \
        xterm && \
    apt-get clean

# Update pip to latest. The version install by the Ubuntu system package is old
# and can't build the pycairo wheel.
RUN pip3 install --no-cache-dir --upgrade pip

RUN mkdir -p $HOME/.parallel && \
    touch $HOME/.parallel/will-cite  # Silence citation warning

# Tesseract data files for Legacy *and* LSTM engines.
ADD https://github.com/tesseract-ocr/tessdata/raw/590567f/deu.traineddata \
    https://github.com/tesseract-ocr/tessdata/raw/590567f/eng.traineddata \
    https://github.com/tesseract-ocr/tessdata/raw/590567f/osd.traineddata \
    https://github.com/tesseract-ocr/tessdata/raw/590567f/pol.traineddata \
    /usr/share/tesseract-ocr/4.00/tessdata/
