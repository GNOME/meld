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
### Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import os

_locale_dir = ( #LOCALEDIR#
)
_help_dir = ( #HELPDIR#
)
_share_dir = ( #SHAREDIR#
)

appdir = os.path.dirname(__file__)

if not _locale_dir: _locale_dir = os.path.join(appdir,"po")
if not _help_dir:    _help_dir  = os.path.join(appdir,"help")
if not _share_dir:  _share_dir  = appdir

def locale_dir(*args): # i18n files
    return os.path.join(_locale_dir, *args)

def help_dir(*args): # help
    return os.path.join(_help_dir, *args)

def share_dir(*args): # glade + pixmaps
    return os.path.join(_share_dir, *args)

