FROM stb_tester/stb-tester-virtual-stb:latest

MAINTAINER david@stb-tester.com

RUN sudo apt-get update && \
    sudo apt-get install -y chromium-browser wget unzip

ADD download-static-assets.sh /tmp/download-static-assets.sh
RUN /tmp/download-static-assets.sh && \
    sudo rm /tmp/download-static-assets.sh

RUN mkdir -p /var/lib/stbt/.config/chromium/Default/ /var/lib/stbt/.config/stbt
ADD Preferences /var/lib/stbt/.config/chromium/Default/Preferences
ADD key-mapping.conf /var/lib/stbt/.config/stbt/key-mapping.conf

ADD virtual-stb /var/lib/stbt/virtual-stb

CMD chromium-browser --no-sandbox --app=file:///var/lib/stbt/virtual-stb/index.html
