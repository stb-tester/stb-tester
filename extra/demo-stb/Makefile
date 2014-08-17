install-dependencies: virtual-stb/LigatureSymbols-2.11.ttf
	wget -P virtual-stb -qN http://code.jquery.com/jquery-2.1.1.min.js
	wget -P virtual-stb -qN http://mirrorblender.top-ix.org/peach/bigbuckbunny_movies/big_buck_bunny_480p_stereo.ogg
	wget -P virtual-stb -qN https://archive.org/download/ElephantsDream/ed_1024.ogv
	wget -P virtual-stb -qN http://download.blender.org/durian/trailer/sintel_trailer-720p.ogv
	wget -P virtual-stb -qN http://blender-mirror.kino3d.org/mango/download.blender.org/demo/movies/ToS/tears_of_steel_720p.mkv
	wget -qN -O virtual-stb/thumbnail-bbb.jpg https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Big_buck_bunny_poster_big.jpg/170px-Big_buck_bunny_poster_big.jpg
	wget -qN -O virtual-stb/thumbnail-ed.jpg http://content9.flixster.com/movie/11/15/64/11156431_800.jpg
	wget -qN -O virtual-stb/thumbnail-sintel.jpg http://www.sintel.org/wp-content/uploads/2010/09/sintel_poster.jpg
	wget -qN -O virtual-stb/thumbnail-tos.png https://upload.wikimedia.org/wikipedia/commons/thumb/7/70/Tos-poster.png/256px-Tos-poster.png
	wget -qN -O virtual-stb/thumbnail-hercules.jpg http://www.ropeofsilicon.com/wp-content/uploads/2012/11/hercules-poster1.jpg

virtual-stb/LigatureSymbols-2.11.ttf:
	wget -q http://kudakurage.com/ligature_symbols/LigatureSymbols.zip
	unzip -p LigatureSymbols.zip LigatureSymbols/$(notdir $@) > $@
	rm -f LigatureSymbols.zip

docker-build :
	docker build -t $(docker_prefix)virtual-stb-stbt-demo . && \
	printf "Now run with:\n\n" && \
	printf "    stbt virtual-stb --docker-image=$(docker_prefix)virtual-stb-stbt-demo\n"

.DELETE_ON_ERROR:
.PHONY : docker-build install-dependencies
