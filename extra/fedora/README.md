The Dockerfile in this directory allows me to build stb-tester packages for
Fedora when Fedora isn't the host OS on my PC. `fedora-shell.sh` allows me to
conveniently run any command inside that docker container, with full access to
my stb-tester working copy.

To package a new stb-tester release for Fedora:

    extra/fedora/fedora-shell.sh -c "make srpm; sudo make rpm"
    extra/fedora/test-rpm.sh stb-tester-$version-1.fc20.x86_64.rpm
    extra/fedora/fedora-shell.sh -c \
        "extra/fedora/copr-publish.sh stb-tester-$version-1.fc20.src.rpm"
