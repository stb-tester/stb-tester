Name: stb-tester
Version: 0.18
Release: 1%{?dist}
Summary: Automated user interface testing for set-top boxes
Group: Development/Tools
URL: http://stb-tester.com
License: LGPLv2.1+
Source: %{name}-%{version}.tar.gz
BuildArch: noarch
BuildRequires: python-docutils

Requires: curl
Requires: gstreamer
Requires: gstreamer-plugins-bad-free
Requires: gstreamer-plugins-base
Requires: gstreamer-plugins-good
Requires: gstreamer-python
Requires: opencv
Requires: opencv-python
Requires: openssh-clients
Requires: pygtk2
Requires: pylint
Requires: python >= 2.7
Requires: python-jinja2
Requires: tesseract

%description
stb-tester tests a set-top-box by issuing commands to it using a remote-control
and checking that it has done the right thing by analysing what is on screen.
Test scripts are written in Python and can be generated with the `stbt record`
command.

%prep
%setup

%build
make prefix=/usr sysconfdir=/etc

%install
make install prefix=/usr sysconfdir=/etc DESTDIR=${RPM_BUILD_ROOT}

%files
%defattr(-,root,root,-)

/usr/bin/stbt
/usr/bin/irnetbox-proxy
/usr/libexec/stbt
/usr/share/man/man1
/etc/bash_completion.d/stbt
%config(noreplace) /etc/stbt
