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

"""Module of commonly used helper classes and functions

"""

from __future__ import generators
import copy
import sys
import os
import select
import popen2
import gtk

def run_dialog( text, messagetype=gtk.MESSAGE_WARNING, buttonstype=gtk.BUTTONS_OK):
    d = gtk.MessageDialog(None,
        gtk.DIALOG_DESTROY_WITH_PARENT,
        messagetype,
        buttonstype,
        '<span weight="bold" size="larger">%s</span>' % text)
    d.set_has_separator(0)
    d.vbox.set_spacing(12)
    hbox = d.vbox.get_children()[0]
    hbox.set_spacing(12)
    d.image.set_alignment(0.5, 0)
    d.image.set_padding(12, 12)
    d.label.set_use_markup(1)
    d.label.set_padding(12, 12)
    ret = d.run()
    d.destroy()
    return ret

def appdir(pathin):
    """Return where the application is installed.
    """
    where = os.path.dirname(sys.argv[0])
    pathout = os.path.join( where, pathin )
    if not os.path.exists(pathout):
        run_dialog("Cannot find '%s'\nI looked in '%s'\n(%s)" % (pathin,where,pathout), gtk.MESSAGE_ERROR)
        sys.exit(1)
    return pathout

class struct:
    """Similar to a dictionary except that members may be accessed as s.member.

    Usage:
    s = struct(a=10, b=20, d={"cat":"dog"} )
    print s.a + s.b
    """
    def __init__(self, **args):
        self.__dict__.update(args)
    def __repr__(self):
        r = ["<"]
        for i in self.__dict__.keys():
            r.append("%s=%s" % (i, getattr(self,i)))
        r.append(">\n")
        return " ".join(r)

def all_equal(list):
    """Return true if all members of the list are equal to the first.

    An empty list is considered to have all elements equal.
    """
    if len(list):
        first = list[0]
        for n in list[1:]:
            if n != first:
                return 0
    return 1
    
def shorten_names(*names):
    """Remove redunant parts of a list of names (e.g. /tmp/foo{1,2} -> foo{1,2}
    """
    prefix = os.path.commonprefix( names )
    try:
        prefixslash = prefix.rindex("/") + 1
    except ValueError:
        prefixslash = 0

    names = map( lambda x: x[prefixslash:], names) # remove common prefix
    paths = map( lambda x: x.split("/"), names) # split on /

    try:
        basenames = map(lambda x: x[-1], paths)
    except IndexError:
        pass
    else:
        if all_equal(basenames):
            def firstpart(list):
                if len(list) > 1: return "[%s] " % list[0]
                else: return ""
            roots = map(firstpart, paths)
            base = basenames[0].strip()
            return [ r+base for r in roots ]
    # no common path. empty names get changed to "[None]"
    return map( lambda x: x or "[None]", names)

def look(s, o):
    """Return a list of attributes in 'o' which contain the string 's'
    """
    return filter(lambda x:x.find(s)!=-1, dir(o))

def ilook(s, o):
    """Return a list of attributes in 'o' which contain the string 's' ignoring case. 
    """
    return filter(lambda x:x.lower().find(s)!=-1, dir(o))

def all(o):
    """Return a list of all the attributes in 'o' along with their values
    """
    return "\n".join( ["%s\t%s" % (x,getattr(o,x)) for x in dir(o)] )

def read_pipe_iter(command, yield_interval=0.1, workdir=None):
    """Read the output of a shell command iteratively.

    Each time 'callback_interval' seconds pass without reading any data,
    this function yeilds None.
    When all the data is read, the entire string is yeilded.
    If 'workdir' is specified the command is run from that directory.
    """
    if workdir:
        savepwd = os.getcwd()
        os.chdir( workdir )
    pipe = popen2.Popen3(command, capturestderr=1)
    childin, childout, childerr = pipe.tochild, pipe.fromchild, pipe.childerr
    childin.close()
    if workdir:
        os.chdir( savepwd )
    bits = []
    while len(bits)==0 or bits[-1]!="":
        state = select.select([childout], [], [childout], yield_interval)
        if len(state[0])==0:
            if len(state[2])==0:
                yield None
            else:
                raise "Error reading pipe"
        else:
            try:
                bits.append( childout.read(4096) ) # get buffer size
            except IOError:
                break # ick need to fix
    status = pipe.wait()
    #if status:
        #raise IOError("%i %s" %(status,childerr.read()))
    yield "".join(bits)

def write_pipe(command, text):
    """Write 'text' into a shell command.
    """
    childin, childout, childerr = os.popen3(command, "w")
    childin.write(text)
    childin.close()

def safe_apply(object, method, args):
    """Call 'object.method(args)' if 'object' has an attribute named 'method'.

    If 'object' has no method 'method' this is a no-op.
    """
    try:
        m = getattr(object,method)
    except AttributeError:
        pass
    else:
        # allow single arguments to be passed as is.
        if type(args) != type(()):
            args = (args,)
        apply(m, args)

def clamp(val, lower, upper):
    """Clamp 'val' to the inclusive range [lower,upper].
    """
    assert lower <= upper
    return min( max(val, lower), upper)

def enumerate(seq):
    """Emulate enumerate from python2.3.
    """
    i = 0
    for s in seq:
        yield (i,s)
        i += 1

def commonprefix(dirs):
    """Given a list of pathnames, returns the longest common leading component.
    """
    if not dirs: return ''
    n = copy.copy(dirs)
    for i in range(len(n)):
        n[i] = n[i].split(os.sep)
    prefix = n[0]
    for item in n:
        for i in range(len(prefix)):
            if prefix[:i+1] <> item[:i+1]:
                prefix = prefix[:i]
                if i == 0: return ''
                break
    return os.sep.join(prefix)

def escape(s):
    """Replace special characters '&', '<' and '>' by SGML entities.
    """
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    return s

