# If you change this dockerfile, run `make publish-ci-docker-images`.

FROM ubuntu:26.04

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
        pycodestyle \
        pylint \
        python3-docutils \
        python3-gi \
        python3-ipython \
        python3-jinja2 \
        python3-libcec \
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

RUN pip3 install --break-system-packages pyright[nodejs] && pyright --version

RUN mkdir -p $HOME/.parallel && \
    touch $HOME/.parallel/will-cite  # Silence citation warning

# Tesseract data files for Legacy *and* LSTM engines.
ADD https://github.com/tesseract-ocr/tessdata/raw/590567f/deu.traineddata \
    https://github.com/tesseract-ocr/tessdata/raw/590567f/eng.traineddata \
    https://github.com/tesseract-ocr/tessdata/raw/590567f/osd.traineddata \
    https://github.com/tesseract-ocr/tessdata/raw/590567f/pol.traineddata \
    /usr/share/tesseract-ocr/5/tessdata/

# 26.04's python3-libcec is unusable: it installs cec.py into a directory that
# isn't on sys.path, and it's missing _pycec.so (Debian bug #1134169). It was
# fixed in libcec 8.1.6+dfsg2-1, which is too late for 26.04 but is in 27.04,
# and those packages install on 26.04 without dragging in a newer libc or
# python.
RUN export DEBIAN_FRONTEND=noninteractive && \
    printf 'Types: deb\nURIs: http://archive.ubuntu.com/ubuntu/\nSuites: tenacious\nComponents: universe\nSigned-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n' \
        > /etc/apt/sources.list.d/tenacious.sources && \
    printf 'Package: *\nPin: release n=tenacious\nPin-Priority: -10\n\nPackage: libcec8 python3-libcec\nPin: release n=tenacious\nPin-Priority: 500\n' \
        > /etc/apt/preferences.d/tenacious && \
    apt-get update && \
    apt-get install -y --no-install-recommends python3-libcec && \
    rm /etc/apt/sources.list.d/tenacious.sources /etc/apt/preferences.d/tenacious && \
    apt-get update && \
    apt-get clean && \
    python3 -c "import cec"
