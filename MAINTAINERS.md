# Documentation for maintainers of the stb-tester project

### Release checklist

[Create an issue called "vXX release"](
https://github.com/stb-tester/stb-tester/issues/new?title=vXX%20release).
Paste in the following checklists:

* [ ] Check the Travis build status on master:
  <https://github.com/stb-tester/stb-tester/branches>
* [ ] `make check enable_stbt_camera=yes` (run this locally, because Travis
  doesn't run the stbt-camera tests nor a few other tests)
* [ ] Update docs/release-notes.md & commit
* [ ] `git tag -a v$version`
* [ ] `git push origin v$version`

Ubuntu packages:

* [ ] `extra/debian/ubuntu-shell.sh -c "make deb"`
* [ ] `extra/debian/test-deb.sh stb-tester*_$version-1_amd64.deb`
* [ ] `make ppa-publish`

Announce on:

* [ ] Stb-tester.com blog
* [ ] Mailing list
* [ ] Twitter
