virtual-stb/big_buck_bunny_480p_stereo.ogg:
	cd $(dirname $@) && \
	wget http://mirror.bigbuckbunny.de/peach/bigbuckbunny_movies/$(notdir $@)

docker-build :
	docker build -t $(docker_prefix)virtual-stb-stbt-demo . && \
	printf "Now run with:\n\n" && \
	printf "    stbt virtual-stb --docker-image=$(docker_prefix)virtual-stb-stbt-demo\n"

.DELETE_ON_ERROR:
.PHONY : docker-build
