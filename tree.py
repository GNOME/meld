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
import gtk
import misc
import gnomeglade

COL_PATH, COL_STATE, COL_TEXT, COL_ICON, COL_END = range(5)

STATE_NONE, STATE_NORMAL, STATE_NEW, STATE_MODIFIED, STATE_REMOVED, STATE_MISSING = range(6)

load = lambda x,s=14: gnomeglade.load_pixbuf(misc.appdir("glade2/pixmaps/"+x), s)
pixbuf_folder = load("i-directory.png")
pixbuf_file = load("i-regular.png")
pixbuf_file_new = load("i-new.png")
pixbuf_file_changed = load("i-changed.png")

class DiffTreeStore(gtk.TreeStore):
    def __init__(self, ntree = 3):
        types = [type("")] * COL_END * ntree
        types[COL_ICON*ntree:COL_ICON*ntree+ntree] = [type(pixbuf_file)] * ntree
        gtk.TreeStore.__init__(self, *types)
        self.ntree = ntree

    def add_entries(self, parent, names):
        child = self.append(parent)
        for i,f in misc.enumerate(names):
            self.set_value( child, self.column_index(COL_PATH,i), f)
        return child

    def add_empty(self, parent, text="empty folder"):
        child = self.append(parent)
        for i in range(self.ntree):
            self.set_value(child, self.column_index(COL_PATH,i), None)
            self.set_value(child, self.column_index(COL_TEXT,i),
                '<span foreground="#999999" style="italic">%s</span>' % text)
        return child

    def add_error(self, parent, msg, pane):
        err = self.append(parent)
        self.set_value(err, self.column_index(COL_TEXT,pane),
            '<span foreground="#ff0000" background="yellow" weight="bold">*** %s ***</span>' % msg )
        
    def value_paths(self, iter):
        return [ self.value_path(iter, i) for i in range(self.ntree) ]
    def value_path(self, iter, pane):
        return self.get_value(iter, self.column_index(COL_PATH, pane) )
    def column_index(self, col, pane):
        return self.ntree * col + pane

    def set_state(self, iter, pane, state, isdir=0):
        if isdir:
            pixbuf_normal = pixbuf_folder
            pixbuf_new = pixbuf_folder
            pixbuf_modified = pixbuf_folder
        else:
            pixbuf_normal = pixbuf_file
            pixbuf_new = pixbuf_file_new
            pixbuf_modified = pixbuf_file_changed
        name = os.path.basename( self.get_value(iter, self.column_index(COL_PATH,pane)) )
        TEXT = self.column_index(COL_TEXT,pane)
        ICON = self.column_index(COL_ICON,pane)
        if state == STATE_NONE:
            self.set_value(iter, TEXT,
                '<span foreground="#888888">%s</span>' % name)
            self.set_value(iter, ICON, pixbuf_normal)
        elif state == STATE_NORMAL:
            self.set_value(iter, TEXT,
                '<span foreground="black">%s</span>' % name)
            self.set_value(iter, ICON, pixbuf_normal)
        elif state == STATE_NEW:
            self.set_value(iter, TEXT,
                '<span foreground="#008800" weight="bold">%s</span>' % name)
            self.set_value(iter, ICON, pixbuf_new)
        elif state == STATE_MODIFIED:
            self.set_value(iter, TEXT,
                '<span foreground="#880000" weight="bold">%s</span>' % name)
            self.set_value(iter, ICON, pixbuf_modified)
        elif state == STATE_REMOVED:
            self.set_value(iter, TEXT,
                '<span foreground="#880000" strikethrough="true" weight="bold">%s</span>' % name)
            self.set_value(iter, ICON, pixbuf_modified)
        elif state == STATE_MISSING:
            self.set_value(iter, TEXT,
                '<span foreground="#000088" strikethrough="true" weight="bold">%s</span>' % name)
            self.set_value(iter, ICON, None)
        else:
            raise "HUH? %i" % state

