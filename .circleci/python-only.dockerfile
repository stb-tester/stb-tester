# If you change this dockerfile, run `make publish-ci-docker-images`.

FROM ubuntu:18.04

RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        git \
        gzip \
        language-pack-en \
        pylint3 \
        python3-pip \
        python3-pytest \
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
