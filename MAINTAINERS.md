# Documentation for maintainers of the stb-tester project

To make a release:

* `make check enable_stbt_camera=yes`
* Update docs/release-notes.md
* `git tag -a vXX && git push vXX`

* Fedora packages:

        extra/fedora/fedora-shell.sh -c "make srpm && sudo make rpm"
        extra/fedora/test-rpm.sh stb-tester-$version-1.fc20.x86_64.rpm
        extra/fedora/copr-publish.sh stb-tester-$version-1.fc20.src.rpm

* Ubuntu packages:

        extra/debian/ubuntu-shell.sh -c "make deb"
        extra/debian/test-deb.sh stb-tester*_$version-1_amd64.deb
        make ppa-publish

* Announce on <https://stb-tester.com/blog> and twitter.
