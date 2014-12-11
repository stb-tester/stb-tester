#!/bin/sh -x

this_dir=$(dirname $0) &&
stbt_dir=$(cd $this_dir/../.. && pwd) &&

build_deps=$(grep 'BuildRequires:' $this_dir/stb-tester.spec.in | awk '{printf "%s ",$2 }') &&

(
	cat $this_dir/Dockerfile
	echo
	echo "RUN sudo yum install -y copr-cli git make rpm-build wget yum-utils $build_deps"
) | docker build -t stbtester/stb-tester-test-build-fedora-package - &&

docker run -v $stbt_dir:/usr/src/stb-tester:ro \
	-v /home/stb-tester/rpmbuild \
	--name test-fedora-rpm-builder \
	stbtester/stb-tester-test-build-fedora-package \
	'git clone /usr/src/stb-tester &&
	cd stb-tester &&
	make srpm &&
	rpmbuild --rebuild *.src.rpm' &&
trap "docker rm test-fedora-rpm-builder" EXIT &&

docker build -t stbtester/stb-tester-test-fedora-package - <$this_dir/Dockerfile &&

docker run --rm --volumes-from test-fedora-rpm-builder \
	-v $stbt_dir:/usr/src/stb-tester:ro \
	stbtester/stb-tester-test-fedora-package \
	'sudo yum install -y rpmbuild/RPMS/*/*stb-tester*.rpm &&
	stbt --version &&
	stbt --help &&
	man stbt | cat &&
	cd /usr/src/stb-tester &&
	./tests/run-tests.sh -i tests/test-match.sh'
