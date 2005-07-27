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
import gobject
import os

class Folder:
    """
    self.entries : name of filesystem entries, folders first
    self.children : children entries. len(children) == num folders
    self.extra : extra data for each entry. len(extra) == num entries
    """
    def __init__(self, fullpath, parent):
        self.parent = parent
        dirs, files, extra = self.listdir(fullpath)
        self.names = dirs + files
        self.children = [None] * len(dirs)
        self.extra = extra
        if len(self.names) == 0:
            self.names = ("<i>(Empty)</i>",)
            self.extra = None

    def listdir(self, path):
        badext = {"pyc":0, "swp":0} #XXX
        try:
            ent = [ e for e in os.listdir( path )
                    if not e.split(".")[-1] in badext ]
        except OSError:
            return [], [], []
        else:
            ent.sort()
            ent = [ (e, os.path.isdir( os.path.join(path, e) )) for e in ent ]
            dirs = [ e[0] for e in ent if e[1] ]
            rest = [ e[0] for e in ent if not e[1] ]
            return dirs, rest, [str(i) for i in range(len(ent))]

    def fullpath(self):
        cur, parent = self, self.parent
        path = []
        while parent:
            path.append( parent.names[ parent.children.index(cur) ] )
            cur, parent = parent, parent.parent
        path.reverse()
        return "/".join(path) or "."

    def expand_child(self, i):
        """Expand the i'th child and return the number of its children."""
        if i < len(self.children):
            if self.children[i] == None:
                newpath = os.path.join( self.fullpath(), self.names[i] )
                self.children[i] = Folder( newpath, self )
            return len(self.children[i].names)
        return None

    def __repr__(self):
        return "(%i) %s" % (id(self), self.fullpath())


class RootFolder:
    def __init__(self):
        self.names = []
        self.children = []
        self.extra = []
        self.parent = None
    def add_filesystem(self, name):
        name = os.path.abspath(name)
        self.names.append( name )
        self.children.append( Folder(name, self) )
        self.extra.append( ("",) )
    def fullpath(self):
        return ""
    def expand_child(self, i):
        """Return the number of children of child i"""
        return len(self.children[i].names)

def dump(self, indent=0):
    if not self:
        return
    for i in range(len(self.children)):
        print indent*" ", "+", self.names[i]
        dump( self.children[i], indent+2)
    for i in range(len(self.children), len(self.names)):
        print indent*" ", "_", self.names[i]

class FileSystemIter:
    __slots__= ("entry", "index")

    TYPE_UNKNOWN = 0
    TYPE_FOLDER = 1
    TYPE_FILE = 2

    def __init__(self, e, i):
        self.entry, self.index = e, i
    def __repr__(self):
        return "(%s)" % self.entry.names[self.index]
    def isdir(self):
        return self.index < len(self.entry.children)
    def get_type(self):
        if self.index < len(self.entry.children):
            return self.TYPE_FOLDER
        elif self.entry.names[self.index].find("<i>") == -1:
            return self.TYPE_FILE
        else:
            return self.TYPE_UNKNOWN
    def num_children(self):
        if self.isdir():
            return self.entry.expand_child(self.index)
        return 0
    def get_parent(self):
        parent = self.entry.parent
        if parent:
            idx = parent.children.index(self.entry)
            return FileSystemIter(parent, idx)
        return None
    def get_path(self):
        cur, parent = self.entry, self.entry.parent
        path = [ self.index ]
        while parent:
            path.append( parent.children.index(cur) )
            cur, parent = parent, parent.parent
        path.reverse()
        return tuple(path)
    def _name_internal(self, start):
        it = start
        path = []
        while it:
            path.append( it.name() )
            it = it.get_parent()
        path.reverse()
        return "/".join(path)
    def get_extra(self, col):
        return self.entry.extra[self.index][col]
    def dirname(self):
        return self._name_internal(self.get_parent())
    def fullname(self):
        return self._name_internal(self)
    def name(self):
        return self.entry.names[self.index]
    def get_next(self):
        if self.index+1 < len(self.entry.names):
            return FileSystemIter(self.entry, self.index+1)
        return None
    def get_first_child(self):
        if self.entry.expand_child(self.index):
            return FileSystemIter( self.entry.children[self.index], 0)
        return None
    def get_nth_child(self, n):
        self.entry.expand_child(self.index)
        return FileSystemIter(self.entry.children[self.index], n)

class FileSystemTreeModel(gtk.GenericTreeModel):
    '''This class represents the model of a tree.  The iterators used
    to represent positions are converted to python objects when passed
    to the on_* methods.  This means you can use any python object to
    represent a node in the tree.  The None object represents a NULL
    iterator.
    '''
    BUILTIN_COLS = [gobject.TYPE_STRING, gobject.TYPE_STRING]

    def __init__(self, *extracols):
        gtk.GenericTreeModel.__init__(self)
        self.root = RootFolder()
        self.column_types = self.BUILTIN_COLS + list(extracols)

    def add_filesystem(self, fspath):
        path = len(self.root.children)
        self.root.add_filesystem(fspath)
        it = self.get_iter(path)
        self.row_inserted(path, it)
        self.row_has_child_toggled(path, it)

    def on_get_path(self, it):
        '''returns the tree path (a tuple of indices at the various levels)
        for a particular iter.'''
        return it.get_path()

    def on_get_flags(self):
        '''returns the GtkTreeModelFlags for this particular type of model'''
        return 0#gtk.TREE_MODEL_ITERS_PERSIST

    def on_get_n_columns(self):
        '''returns the number of columns in the model'''
        return len(self.column_types)

    def on_get_column_type(self, col):
        '''returns the type of a column in the model'''
        return self.column_types[col]

    def on_get_iter(self, path):
        '''returns the iter corresponding to the given path.'''
        if len(self.root.names):
            cur = self.root
            for i in path[:-1]:
                cur = cur.children[i]
            return FileSystemIter(cur, path[-1])
        return None

    def on_get_value(self, it, column):
        '''returns the value stored in a particular column for the iter'''
        self.getters = [
            lambda i : it.name(),
            lambda i : it.dirname()
        ]
        return self.getters[column](it)

    # directions

    def on_iter_next(self, it):
        '''returns the next iter at this level of the tree'''
        return it.get_next()

    def on_iter_children(self, it):
        '''returns the first child of this it'''
        if it:
            return it.get_first_child()
        elif len(self.root.names): # top
            return FileSystemIter( self.root, 0 )
        else:
            return None

    def on_iter_has_child(self, it):
        '''returns true if this it has children'''
        return it and it.isdir()

    def on_iter_n_children(self, it):
        '''returns the number of children of this iter'''
        if it:
            return it.num_children()
        return 0

    def on_iter_nth_child(self, it, n):
        '''returns the nth child of this iter'''
        if it:
            return it.get_nth_child(n)
        else: # top
            return FileSystemIter(self.root, n)

    def on_iter_parent(self, it):
        '''returns the parent of this iter'''
        return it.get_parent()

