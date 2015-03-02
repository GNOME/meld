
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

* Python 2.7
* GTK+ 3.6
* GLib 2.34
* PyGObject 3.8
* GtkSourceView 3.6


Running
-------

Meld can be run directly from this directory. Just type:

 * `bin/meld`

Alternatively, you can install Meld system-wide by running:

 * `python setup.py install`

or if you're on Ubuntu, instead try:

 * `python setup.py install --prefix=/usr`

...but you should probably just get a RPM/deb/installer instead, depending on
your system. Meld packages are available for just about every *nix
distribution.

For Windows users, MSIs are available from the Meld home page.

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

    python setup.py --no-compile-schemas install

**not** this:

    python setup.py install --no-compile-schemas


Contacting
----------

Home page:      http://meldmerge.org  
Documentation:  http://meldmerge.org/help  
Wiki:           https://wiki.gnome.org/Apps/Meld  
Mailing list:   https://mail.gnome.org/mailman/listinfo/meld-list
