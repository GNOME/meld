#! /usr/bin/env python2.2

import os
import math
import gtk
import gobject
import gnomeglade
import misc
import undo

gdk = gtk.gdk

################################################################################
#
# Local Functions
#
################################################################################

def _clamp(val, lower, upper):
    assert lower <= upper
    return min( max(val, lower), upper)

join = os.path.join

################################################################################
#
# MyTreeModel
#
################################################################################

class FileTreeModel(gtk.GenericTreeModel):

    def __init__(self, root):
        gtk.GenericTreeModel.__init__(self)
        self.root = root
        self.cache = {}
        self.state = {}

    def contents(self, p):
        try:
            return self.cache[p][0] + self.cache[p][1]
        except KeyError:
            #print "contents", p
            try:
                e = os.listdir( join(self.root,p) )
            except OSError, err:
                e = ["(Permission Denied)" + str(err)]
            e.sort()
            d = filter(lambda x: os.path.isdir( join(self.root,p,x) ), e)
            f = filter(lambda x: x not in d, e)
            self.cache[p] = (d,f)
            return d + f

    def isdir(self, p):
        #if p==".": return 1
        d,f = os.path.split(p)
        #if not d: d2 = "."
        if not self.cache.has_key(d):
            self.contents(d)
        i = f in self.cache[d][0]
        #print "isdir?", p, "==", i, d,f
        return i

    def on_get_flags(self):
        '''returns the GtkTreeModelFlags for this particular type of model'''
        return 0

    def on_get_n_columns(self):
        '''returns the number of columns in the model'''
        return 2

    def on_get_column_type(self, index):
        '''returns the type of a column in the model'''
        return gobject.TYPE_STRING

    def on_get_path(self, iter):
        '''returns the tree path (a tuple of indices) for a particular node.'''
        r = []
        p = ""
        for i in range(len(iter)):
            try:
                r.append( self.contents(p).index( iter[i] ) )
            except ValueError:
                return None
            p = join(p, iter[i])
        return tuple(r)

    def on_get_iter(self, path):
        '''returns the iter corresponding to the given path.'''
        #print "on_get_iter", path,
        p = ""
        iter = []
        for i in path:
            files = self.contents(p)
            try:
                iter.append(files[i])
            except IndexError:
                iter.append("(Empty)")
            p = "/".join(iter)
        #print "return", iter
        return iter

    def on_get_value(self, iter, n):
        '''returns the value stored in a particular column for the node'''
        #print "on_get_value", iter, n,
        if n==0:
            r = iter[-1]
        else:
            r = self.state.get("/".join(iter), "")
            if n == 1:
                return {"":"#000000", "only":"#dd0000", "changed":"#ff0000"}[r]
            else:
                return r
        #print "return", r
        return r

    def on_iter_next(self, iter):
        '''returns the next iter at this level of the tree'''
        #print "on_iter_next", iter,
        parent = iter[:-1]
        files = self.contents("/".join(parent))
        try:
            i = files.index( iter[-1] )
        except ValueError:
            return None
        else:
            if i+1 < len(files):
                r = files[i+1]
                #print "return", r
                return parent + [r]
        #print "return None"
        return None

    def on_iter_children(self, iter):
        '''returns the first child of this node'''
        #print "on_iter_children", iter,
        p = "/".join(iter)
        files = self.contents(p)
        try:
            r = iter + [files[0]]
        except IndexError:
            r = iter + ["(Empty)"]
        #print "return", r
        return r

    def on_iter_has_child(self, iter):
        '''returns true if this node has children'''
        #print "on_iter_has_child", iter,
        p = "/".join(iter)
        isdir = self.isdir(p)
        #print "return", isdir
        return isdir

    def on_iter_n_children(self, iter):
        '''returns the number of children of this node'''
        p = "/".join(iter)
        return len(self.contents(p))

    def on_iter_nth_child(self, iter, n):
        '''returns the nth child of this node'''
        #print "on_iter_nth_child", iter, n,
        if iter == None:
            iter = []
        p = "/".join(iter)
        files = self.contents(p)
        r = iter + files[n:n+1]
        #print "return", r
        return r

    def on_iter_parent(self, iter):
        '''returns the parent of this node'''
        return iter[:-1]

################################################################################
#
# DirDiff
#
################################################################################

MASK_SHIFT, MASK_CTRL, MASK_ALT = 1, 2, 3

class DirDiff(gnomeglade.Component):
    """Two or three way diff of directories"""

    __gsignals__ = {
        'label-changed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_STRING,)),
        'working-hard': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_INT,)),
        'create-diff': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,))
    }

    keylookup = {65505 : MASK_SHIFT, 65507 : MASK_CTRL, 65513: MASK_ALT}

    def __init__(self, root=".", numpanes=2, statusbar=None):
        self.__gobject_init__()
        gnomeglade.Component.__init__(self, misc.appdir("glade2/dirdiff.glade"), "dirdiff")
        self._map_widgets_into_lists( ["treeview", "fileentry", "diffmap", "scrolledwindow", "linkmap"] )
        self.numpanes = 0
        self.set_num_panes(numpanes)
        self.statusbar = statusbar
        self.undosequence = undo.UndoSequence()
        self.location = (".", "../svnrepository/meld")
        self.model = []
        self.lock = 0
        for i in range(2):
            self.model.append( FileTreeModel(self.location[i]) )
            rentext = gtk.CellRendererText()
            column = gtk.TreeViewColumn(self.location[i], rentext, text=0, foreground=1)
            self.treeview[i].append_column(column)
            column = gtk.TreeViewColumn("status", rentext, text=2)
            self.treeview[i].append_column(column)
            self.treeview[i].connect("row-expanded",  lambda v,i,t: self.on_row_expandcollapse(v,i,t,1) )
            self.treeview[i].connect("row-collapsed", lambda v,i,t: self.on_row_expandcollapse(v,i,t,0) )
            self.treeview[i].connect("row-activated", self.on_row_activate )
            self.treeview[i].set_model(self.model[i])
        self.update_differences("")

    def on_row_activate(self, treeview, path, column):
        master = self.treeview.index(treeview)
        file = "/".join(self.model[master].on_get_iter(path))
        if self.model[master].isdir(file):
            if treeview.row_expanded(path):
                treeview.collapse_row(path)
            else:
                treeview.expand_row(path,0)
        else:
            f = map(lambda x: x.root+"/"+file, self.model)
            f = filter(os.path.exists, f)
            self.emit("create-diff", f)

    def update_differences(self, path):
        if path: pre = path +"/"
        else: pre = ""
        for bar in range(2):
            d0 = self.model[0].cache.get(path, ([],[]))[bar]
            d1 = self.model[1].cache.get(path, ([],[]))[bar]
            d = d0, d1
            i0 = 0
            i1 = 0
            #print "*** checking", path
            #print "cache", path, len(d0), len(d1)
            while i0 < len(d0) or i1 < len(d1):
                if i0 == len(d0):
                    self.model[1].state[pre+d1[i1]] = "only"
                    i1 += 1
                elif i1 == len(d1):
                    self.model[0].state[pre+d0[i0]] = "only"
                    i0 += 1
                elif d0[i0] == d1[i1]:
                    if bar != 0:
                        t0 = open(self.model[0].root + "/" + pre+d0[i0]).read()
                        t1 = open(self.model[1].root + "/" + pre+d1[i1]).read()
                        if t0 != t1:
                            self.model[0].state[pre+d0[i0]] = "changed"
                            self.model[1].state[pre+d1[i1]] = "changed"
                    i0 += 1
                    i1 += 1
                elif d0[i0] < d1[i1]:
                    self.model[0].state[pre+d0[i0]] = "only"
                    i0 += 1
                elif d0[i0] > d1[i1]:
                    self.model[1].state[pre+d1[i1]] = "only"
                    i1 += 1
                else:
                    assert 0


    def on_row_expandcollapse(self, masterview, junk, masterpath, expand):
        if self.lock:
            return
        self.lock = 1
        masterindex = self.treeview.index(masterview)
        iter = self.model[masterindex].on_get_iter(masterpath)
        for i in range(2):
            if i != masterindex:
                p = self.model[i].on_get_path(iter)
                if p:
                    if expand:
                        self.treeview[i].expand_row(p,0)
                    else:
                        self.treeview[i].collapse_row(p)
                if expand:
                    self.update_differences("/".join(iter))
        self.lock = 0

    def label_changed(self):
        self.emit("label-changed", "[Dir] %s : %s " % self.location)
    def refresh(*args):
        print "refresh", args
    def on_key_press_event(*args):
        print "key", args
    def on_key_release_event(*args):
        print "key", args

    def set_num_panes(self, numpanes):
        if numpanes != self.numpanes and numpanes in (1,2,3):
            if numpanes == 1:
                map( lambda x: x.hide(), self.linkmap + self.scrolledwindow[1:] + self.fileentry[1:])
            elif numpanes == 2:
                self.linkmap1.hide()
                self.scrolledwindow2.hide()
                self.fileentry2.hide()
            else:
                self.linkmap1.show()
                self.scrolledwindow2.show()
                self.fileentry2.show()
            self.numpanes = numpanes

gobject.type_register(DirDiff)


