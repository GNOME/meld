
About Meld
==========

Meld is a visual diff and merge tool targeted at developers. Meld helps you
compare files, directories, and version controlled projects. It provides
two- and three-way comparison of both files and directories, and supports
many version control systems including Git, Mercurial, Bazaar and Subversion.

Meld helps you review code changes, understand patches, and makes enormous
merge conflicts slightly less painful.

Meld is licensed under the GPL v2 or later.


Requirements
------------

* Python 3.4
* pycairo (Python3 bindings for cairo without GObject layer)
* PyGObject 3.20 (Python3 bindings for GObject introspection)
* gsettings-desktop-schemas

And following packages with GObject introspection:

* GLib 2.36 (meld install also needs GLib binaries like glib-compile-schemas)
* Pango
* PangoCairo
* GTK+ 3.20
* GtkSourceView 3.20 (note that GtkSourceView 4 is not supported)


Build requirements
------------------

* intltool
* itstool
* xmllint

Building Windows MSIs requires:

* cx_Freeze 5
* pywin32/pypiwin32 (optional, for storing version info in Meld.exe)

Running
-------

Meld can be run directly from this source tree directory. Just type:

 * `bin/meld`

Alternatively, you can install Meld system-wide by running:

 * `python3 setup.py install`

or if you're on Ubuntu, instead try:

 * `python3 setup.py install --prefix=/usr`

...but you should probably just get a RPM/deb/installer instead, depending on
your system. Meld packages are available for just about every \*nix
distribution.

For Windows users, MSIs are available from the Meld home page. Also if all
dependencies are installed manually, running from source tree is supported:
 * `python3.exe bin/meld`

For OSX users, Meld can be installed on OSX using MacPorts/Fink/etc. There are
also unofficial native builds available for older releases. See the wiki for
details.


Building
--------

Meld uses standard distutils for building. It supports anything that distutils
supports, and little else.

Additional hacks are added to make life easier for packagers where required,
such as:

* Passing `--no-update-icon-cache` will stop Meld from running
  `gtk-update-icon-cache` post-install
* Passing `--no-compile-schemas` will stop Meld from trying to compile
  gsettings schemas post-install

These arguments need to be passed to `setup.py` itself, *not* to the install
command. In other words, do this:

    python3 setup.py --no-compile-schemas install

**not** this:

    python3 setup.py install --no-compile-schemas

Windows installer can be built with command

    C:\Python34\python.exe setup_win32.py bdist_msi

that creates file `dist/Meld-VERSION-ARCH.msi`

Contributing
------------

Meld uses GNOME's GitLab to track bugs, and user questions and development
discussions happen on the Meld mailing list. The development team is small,
and new contributors are always welcome!

List of issues: https://gitlab.gnome.org/GNOME/meld/issues

Mailing list:   https://mail.gnome.org/mailman/listinfo/meld-list



Links
-----

Home page:      http://meldmerge.org

Documentation:  http://meldmerge.org/help

Wiki:           https://wiki.gnome.org/Apps/Meld
