Summary: A GNOME2 visual diff and merge tool.
Name: meld
Version: 0.8.1
Release: 0
License: GPL
Group: Applications/Text
URL: http://meld.sourceforge.net/

Packager: Dag Wieers <dag@wieers.com>
Vendor: Dag Apt Repository, http://dag.wieers.com/home-made/apt/

Source: http://prdownloads.sourceforge.net/meld/%{name}-%{version}.tgz
BuildRoot: %{_tmppath}/root-%{name}-%{version}
Prefix: %{_prefix}

BuildRequires: pygtk2-devel >= 1.99.14, gnome-python2 >= 1.99.14
BuildRequires: pyorbit-devel >= 1.99

Requires: pygtk2 >= 1.99.14, gnome-python2 >= 1.99, gnome-python2-canvas
Requires: pygtk2-libglade

BuildArch: noarch

%description
Meld is a GNOME2 visual diff and merge tool. It integrates especially
well with CVS. The diff viewer lets you edit files in place (diffs
update dynamically), and a middle column shows detailed changes and
allows merges.

%prep
%setup

%build

%install
%{__rm} -rf %{buildroot}
%{__install} -d -m0755 %{buildroot}%{_datadir}/meld/glade2/pixmaps \
			%{buildroot}%{_datadir}/applications \
			%{buildroot}%{_datadir}/pixmaps \
			%{buildroot}%{_bindir}
%{__install} -m0755 meld %{buildroot}%{_datadir}/meld/
%{__install} -m0644 *.py %{buildroot}%{_datadir}/meld/
%{__install} -m0644 glade2/*.glade* %{buildroot}%{_datadir}/meld/glade2/
%{__install} -m0644 glade2/pixmaps/* %{buildroot}%{_datadir}/meld/glade2/pixmaps/

%{__install} -m0644 glade2/pixmaps/icon.png %{buildroot}%{_datadir}/pixmaps/meld.png

echo "exec %{_datadir}/meld/meld" >%{name}.sh
%{__install} -m0755 meld.sh %{buildroot}%{_bindir}/meld

cat <<EOF >gnome-%{name}.desktop
[Desktop Entry]
Encoding=UTF-8
Version=1.0
Name=Meld Diff Viewer
Type=Application
Comment=Compare and merge your files.
Exec=meld
Icon=meld.png
Terminal=false
EOF

desktop-file-install --vendor gnome                \
	--add-category X-Red-Hat-Base              \
	--add-category Application                 \
	--add-category Utility                     \
	--dir %{buildroot}%{_datadir}/applications \
	gnome-%{name}.desktop

%clean
%{__rm} -rf %{buildroot}

%files
%doc AUTHORS COPYING TODO.txt
%{_bindir}/*
%{_datadir}/meld/
%{_datadir}/applications/*
%{_datadir}/pixmaps/*

%changelog
* Tue May 20 2003 Dag Wieers <dag@wieers.com> - 0.8.1-0
- Updated to release 0.8.1.

* Wed Apr 16 2003 Dag Wieers <dag@wieers.com> - 0.7.1-0
- Updated to release 0.7.1.

* Mon Apr 07 2003 Dag Wieers <dag@wieers.com> - 0.7.0-0
- Updated to release 0.7.0.

* Wed Feb 12 2003 Dag Wieers <dag@wieers.com> - 0.6.6-0
- Initial package. (using DAR)
