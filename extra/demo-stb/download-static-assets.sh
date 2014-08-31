#!/bin/bash -e

mkdir -p virtual-stb
wget -P virtual-stb -N http://code.jquery.com/jquery-2.1.1.min.js
wget -P virtual-stb -N http://mirrorblender.top-ix.org/peach/bigbuckbunny_movies/big_buck_bunny_480p_stereo.ogg
wget -P virtual-stb -N https://archive.org/download/ElephantsDream/ed_1024.ogv
wget -P virtual-stb -N http://download.blender.org/durian/trailer/sintel_trailer-720p.ogv
wget -P virtual-stb -N http://blender-mirror.kino3d.org/mango/download.blender.org/demo/movies/ToS/tears_of_steel_720p.mkv
wget -N -O virtual-stb/thumbnail-bbb.jpg https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Big_buck_bunny_poster_big.jpg/170px-Big_buck_bunny_poster_big.jpg
wget -N -O virtual-stb/thumbnail-ed.jpg http://content9.flixster.com/movie/11/15/64/11156431_800.jpg
wget -N -O virtual-stb/thumbnail-sintel.jpg http://www.sintel.org/wp-content/uploads/2010/09/sintel_poster.jpg
wget -N -O virtual-stb/thumbnail-tos.png https://upload.wikimedia.org/wikipedia/commons/thumb/7/70/Tos-poster.png/256px-Tos-poster.png
wget -N -O virtual-stb/thumbnail-hercules.jpg http://www.ropeofsilicon.com/wp-content/uploads/2012/11/hercules-poster1.jpg

wget http://kudakurage.com/ligature_symbols/LigatureSymbols.zip
unzip -p LigatureSymbols.zip LigatureSymbols/LigatureSymbols-2.11.ttf >virtual-stb/LigatureSymbols-2.11.ttf
rm -f LigatureSymbols.zip
