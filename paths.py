#! /usr/bin/env python

### Copyright (C) 2002-2003 Stephen Kennedy <steve9000@users.sf.net>

### This program is free software; you can redistribute it and/or modify
### it under the terms of the GNU General Public License as published by
### the Free Software Foundation; either version 2 of the License, or
### (at your option) any later version.

### This program is distributed in the hope that it will be useful,
### but WITHOUT ANY WARRANTY; without even the implied warranty of
### MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
### GNU General Public License for more details.

### You should have received a copy of the GNU General Public License
### along with this program; if not, write to the Free Software
### Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import os

if 1: # run in place. packagers change this line
    import sys
    appdir = os.path.dirname(sys.argv[0])
    def locale_dir(*args): # i18n files
        return os.path.join(appdir, "po", *args)

    def lib_dir(*args): # *.py 
        return os.path.join(appdir, *args)

    def doc_dir(*args): # manual
        return os.path.join(appdir, "manual", *args)

    def share_dir(*args): # glade + pixmaps
        return os.path.join(appdir, *args)
else:
    def locale_dir(*args): # i18n files
        return os.path.join("/usr/share/locale", *args)

    def lib_dir(*args): # *.py 
        return os.path.join("/usr/lib/meld", *args)

    def doc_dir(*args): # manual
        return os.path.join("/usr/share/doc/meld", *args)

    def share_dir(*args): # glade + pixmaps
        return os.path.join("/usr/share/meld", *args)

