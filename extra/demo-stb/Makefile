install-dependencies: big_buck_bunny_480p_stereo.ogg LigatureSymbols-2.11.ttf

big_buck_bunny_480p_stereo.ogg:
	wget http://mirror.bigbuckbunny.de/peach/bigbuckbunny_movies/$@

LigatureSymbols-2.11.ttf:
	wget http://kudakurage.com/ligature_symbols/LigatureSymbols.zip
	unzip -p LigatureSymbols.zip LigatureSymbols/$@ > $@
	rm -f LigatureSymbols.zip

.DELETE_ON_ERROR:
