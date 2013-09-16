Name: stb-tester
Version: 0.16
Release: 1%{?dist}
Summary: A video-capture record-playback testing system for set-top-boxes
Group: Development/Tools
URL: http://stb-tester.com
License: LGPLv2.1+
Source: %{name}-%{version}.tar.gz
BuildArch: noarch
BuildRequires: python-docutils

Requires: python >= 2.4
Requires: pygtk2
Requires: gstreamer-python
Requires: gstreamer
Requires: gstreamer-plugins-base
Requires: gstreamer-plugins-good
Requires: gstreamer-plugins-bad-free
Requires: opencv
Requires: opencv-python
Requires: curl
Requires: expect
Requires: openssh-clients

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
/etc/stbt
/etc/bash_completion.d/stbt
