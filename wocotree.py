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

__metaclass__ = type

import gtk

class Tree(gtk.GenericTreeModel):
    def on_get_flags(self):
        pass
    def on_get_n_columns(self):
        pass
    def on_get_column_type(self, index):
        pass
    def on_get_iter(self, path):
        pass
    def on_get_path(self, rowref):
        pass
    def on_get_value(self, rowref, column):
        pass
    def on_iter_next(self, rowref):
        pass
    def on_iter_children(self, parent):
        pass
    def on_iter_has_child(self, rowref):
        pass
    def on_iter_n_children(self, rowref):
        pass
    def on_iter_nth_child(self, parent, n):
        pass
    def on_iter_parent(self, child):
        pass
