### Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>

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
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
### USA.

import os

_locale_dir = ( #LOCALEDIR#
)
_help_dir = ( #HELPDIR#
)
_share_dir = ( #SHAREDIR#
)

appdir = os.path.dirname(os.path.dirname(__file__))

if not _locale_dir: _locale_dir = os.path.join(appdir,"po")
if not _help_dir:    _help_dir  = os.path.join(appdir,"help")
if not _share_dir:  _share_dir  = os.path.join(appdir, "data")

def locale_dir(*args): # i18n files
    return os.path.join(_locale_dir, *args)

def help_dir(*args): # help
    return os.path.join(_help_dir, *args)

def icon_dir(*args):
    if os.path.exists(os.path.join(_share_dir, "data")):
        return os.path.join(_share_dir, "data", "icons", *args)
    else:
        return os.path.join(_share_dir, "icons", *args)

