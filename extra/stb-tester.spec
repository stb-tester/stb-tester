Name: stb-tester
Version: 0.9
Release: 1%{?dist}
Summary: A video-capture record-playback testing system for set-top-boxes
Group: Development/Tools
URL: http://stb-tester.com
License: LGPLv2.1+
Source: %{name}-%{version}.tar.gz
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
BuildRequires: python-docutils
BuildRequires: gstreamer-devel
BuildRequires: gstreamer-plugins-base-devel
BuildRequires: opencv-devel

Requires: python >= 2.4
Requires: pygtk2
Requires: gstreamer-python
Requires: gstreamer
Requires: gstreamer-plugins-base
Requires: opencv

%description
stb-tester tests a set-top-box by issuing commands to it using a remote-control
and checking that it has done the right thing by analysing what is on screen.
Test scripts are written in Python and can be generated with the `stbt record`
command.

%prep
%setup

%build
make prefix=/usr libdir=%{_libdir} sysconfdir=/etc

%install
make install prefix=/usr libdir=%{_libdir} sysconfdir=/etc DESTDIR=${RPM_BUILD_ROOT}

%clean
rm -rf %{buildroot}

%files
%defattr(-,root,root,-)

/usr/bin/stbt
/usr/libexec/stbt
%{_libdir}/gstreamer-0.10/libgst-stb-tester.so
/usr/share/man/man1
/etc/stbt
/etc/bash_completion.d/stbt
