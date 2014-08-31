install-dependencies: download-static-assets.sh
	$<

docker-build :
	docker build -t $(docker_prefix)virtual-stb-stbt-demo . && \
	printf "Now run with:\n\n" && \
	printf "    stbt virtual-stb --docker-image=$(docker_prefix)virtual-stb-stbt-demo\n"

.DELETE_ON_ERROR:
.PHONY : docker-build install-dependencies
