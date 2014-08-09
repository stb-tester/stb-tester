FROM stb-tester-virtual-stb:makefile

MAINTAINER david@stb-tester.com

RUN sudo apt-get update && \
    sudo apt-get install -y chromium-browser curl

RUN mkdir /var/lib/stbt/virtual-stb && \
    curl --fail -o /var/lib/stbt/virtual-stb/big_buck_bunny_480p_stereo.ogg \
        http://mirrorblender.top-ix.org/peach/bigbuckbunny_movies/big_buck_bunny_480p_stereo.ogg

RUN mkdir -p /var/lib/stbt/.config/chromium/Default/ /var/lib/stbt/.config/stbt
ADD Preferences /var/lib/stbt/.config/chromium/Default/Preferences
ADD key-mapping.conf /var/lib/stbt/.config/stbt/key-mapping.conf

ADD virtual-stb /var/lib/stbt/virtual-stb

CMD chromium-browser --no-sandbox --app=file:///var/lib/stbt/virtual-stb/index.html
