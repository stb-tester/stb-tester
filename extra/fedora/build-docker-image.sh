#!/bin/bash

cd $(dirname $0) &&

buildrequires=$(awk '/^BuildRequires:/ {printf "%s ",$2}' stb-tester.spec.in) &&
cat Dockerfile.in |
sed "s/@BUILDREQUIRES@/$buildrequires/" |
docker build -t stbtester/stb-tester-fedora-build-environment -
