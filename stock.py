### Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>

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

import gtk
import gtk.gdk
import paths

__stock_items = (
    # meldapp
    "reportbug",
    "about",
    "filediff-icon",
    "dirdiff-icon",
    "woco-icon",
    "tab-close",

    # version
    "version-diff",
    "version-update",
    "version-commit",
    "version-add",
    "version-remove",

    "filter-normal",
    "filter-modified",
    "filter-ignored",
    "filter-unknown",
)

def register_iconsets(stock_items):
    gdict = globals()
    stock_names = ["STOCK_%s"%item.upper().replace("-","_") for item in stock_items]
    stock_ids = ["meld-%s"%item for item in stock_items]
    for name, id in zip(stock_names, stock_ids):
        gdict[name] = id
    gtk.stock_add( [ (id,None,0,0,None) for id in stock_ids ] )
        
    iconfactory = gtk.IconFactory()
    iconfactory.add_default()
    for id in stock_ids:
        pixbuf = gtk.gdk.pixbuf_new_from_file( paths.share_dir("glade2/pixmaps/%s.png"%id) )
        iconset = gtk.IconSet(pixbuf)
        iconfactory.add(id, iconset)

register_iconsets(__stock_items)

