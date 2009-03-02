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

"""Module of commonly used helper classes and functions

"""

import copy
import os
from gettext import gettext as _
import select
import popen2
import errno
import gobject
import gtk
import shutil
import re
import signal

whitespace_re = re.compile(r"\s")

def shelljoin( command ):
    def quote(s):
        return ((whitespace_re.search(s) == None) and s or ('"%s"' % s))
    return " ".join( [ quote(x) for x in command ] )

def run_dialog( text, parent=None, messagetype=gtk.MESSAGE_WARNING, buttonstype=gtk.BUTTONS_OK, extrabuttons=[]):
    """Run a dialog with text 'text'.
       Extra buttons are passed as tuples of (button label, response id).
    """
    escaped = gobject.markup_escape_text(text)
    d = gtk.MessageDialog(None,
        gtk.DIALOG_DESTROY_WITH_PARENT,
        messagetype,
        buttonstype,
        '<span weight="bold" size="larger">%s</span>' % escaped)
    if parent:
        d.set_transient_for(parent.widget.get_toplevel())
    for b,rid in extrabuttons:
        d.add_button(b,rid)
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

def open_uri(uri, timestamp=0):
    # TODO: should be 2.14 when released
    if gtk.pygtk_version >= (2, 13, 0):
        gtk.show_uri(gtk.gdk.screen_get_default(), uri, timestamp)
    else:
        try:
            import gnome
            gnome.url_show(uri)
        except ImportError:
            pass

# Taken from epiphany
def position_menu_under_widget(menu, widget):
    container = widget.get_ancestor(gtk.Container)

    widget_width, widget_height = widget.size_request()
    menu_width, menu_height = menu.size_request()

    screen = menu.get_screen()
    monitor_num = screen.get_monitor_at_window(widget.window)
    if monitor_num < 0:
        monitor_num = 0
    monitor = screen.get_monitor_geometry(monitor_num)

    x, y = widget.window.get_origin()
    if widget.flags() & gtk.NO_WINDOW:
        x += widget.allocation.x
        y += widget.allocation.y

    if container.get_direction() == gtk.TEXT_DIR_LTR:
        x += widget.allocation.width - widget_width
    else:
        x += widget_width - menu_width

    if (y + widget.allocation.height + menu_height) <= monitor.y + monitor.height:
        y += widget.allocation.height
    elif (y - menu_height) >= monitor.y:
        y -= menu_height
    elif monitor.y + monitor.height - (y + widget.allocation.height) > y:
        y += widget.allocation.height
    else:
        y -= menu_height

    return (x, y, False)

def make_tool_button_widget(label):
    """Make a GtkToolButton label-widget suggestive of a menu dropdown"""
    arrow = gtk.Arrow(gtk.ARROW_DOWN, gtk.SHADOW_NONE)
    label = gtk.Label(label)
    hbox = gtk.HBox(spacing=3)
    hbox.pack_end(arrow)
    hbox.pack_end(label)
    hbox.show_all()
    return hbox

class struct(object):
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
    def __cmp__(self, other):
        return cmp(self.__dict__, other.__dict__)

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
    return map( lambda x: x or _("[None]"), basenames)

def read_pipe_iter(command, errorstream, yield_interval=0.1, workdir=None):
    """Read the output of a shell command iteratively.

    Each time 'callback_interval' seconds pass without reading any data,
    this function yields None.
    When all the data is read, the entire string is yielded.
    If 'workdir' is specified the command is run from that directory.
    """
    class sentinel(object):
        def __del__(self):
            if self.pipe:
                errorstream.write("killing '%s' with pid '%i'\n" % (command[0], self.pipe.pid))
                os.kill(self.pipe.pid, signal.SIGTERM)
                errorstream.write("killed (status was '%i')\n" % self.pipe.wait())
        def __call__(self):
            if workdir:
                savepwd = os.getcwd()
                os.chdir( workdir )
            self.pipe = popen2.Popen3(command, capturestderr=1)
            self.pipe.tochild.close()
            childout, childerr = self.pipe.fromchild, self.pipe.childerr
            if workdir:
                os.chdir( savepwd )
            bits = []
            while len(bits) == 0 or bits[-1] != "":
                state = select.select([childout, childerr], [], [childout, childerr], yield_interval)
                if len(state[0]) == 0:
                    if len(state[2]) == 0:
                        yield None
                    else:
                        raise "Error reading pipe"
                if childout in state[0]:
                    try:
                        bits.append( childout.read(4096) ) # get buffer size
                    except IOError:
                        break # ick need to fix
                if childerr in state[0]:
                    try:
                        errorstream.write( childerr.read(1) ) # how many chars?
                    except IOError:
                        break # ick need to fix
            status = self.pipe.wait()
            errorstream.write( childerr.read() )
            self.pipe = None
            if status:
                errorstream.write("Exit code: %i\n" % status)
            yield "".join(bits)
    return sentinel()()

def write_pipe(command, text):
    """Write 'text' into a shell command.
    """
    pipe = popen2.Popen3(command, capturestderr=1)
    pipe.tochild.write(text)
    pipe.tochild.close()
    return pipe.wait()

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
            if prefix[:i+1] != item[:i+1]:
                prefix = prefix[:i]
                if i == 0: return ''
                break
    return os.sep.join(prefix)

def escape(s):
    """Replace special characters by SGML entities.
    """
    entities = ("&&amp;", "<&lt;", ">&gt;")
    for e in entities:
        s = s.replace(e[0], e[1:])
    return s

def unescape(s):
    """Inverse of escape.
    """
    entities = (">&gt;", "<&lt;", "&&amp;")
    for e in entities:
        s = s.replace(e[1:], e[0])
    return s

def copy2(src, dst):
    """Like shutil.copy2 but ignores chmod errors.
    See [Bug 568000] Copying to NTFS fails
    """
    if os.path.isdir(dst):
        dst = os.path.join(dst, os.path.basename(src))
    shutil.copyfile(src, dst)
    try:
        shutil.copystat(src, dst)
    except OSError, e:
        if e.errno != errno.EPERM:
            raise

def copytree(src, dst, symlinks=1):
    try:
        os.mkdir(dst)
    except OSError, e:
        if e.errno != errno.EEXIST:
            raise
    names = os.listdir(src)
    for name in names:
        srcname = os.path.join(src, name)
        dstname = os.path.join(dst, name)
        if symlinks and os.path.islink(srcname):
            linkto = os.readlink(srcname)
            os.symlink(linkto, dstname)
        elif os.path.isdir(srcname):
            copytree(srcname, dstname, symlinks)
        else:
            copy2(srcname, dstname)

def shell_to_regex(pat):
    """Translate a shell PATTERN to a regular expression.

    Based on fnmatch.translate(). We also handle {a,b,c} where fnmatch does not.
    """

    i, n = 0, len(pat)
    res = ''
    while i < n:
        c = pat[i]
        i += 1
        if c == '\\':
            try:
                c = pat[i]
            except IndexError:
                pass
            else:
                i += 1
                res += re.escape(c)
        elif c == '*':
            res += '.*'
        elif c == '?':
            res += '.'
        elif c == '[':
            try:
                j = pat.index(']', i)
            except ValueError:
                res += r'\['
            else:
                stuff = pat[i:j]
                i = j+1
                if stuff[0] == '!':
                    stuff = '^%s' % stuff[1:]
                elif stuff[0] == '^':
                    stuff = r'\^%s' % stuff[1:]
                res += '[%s]' % stuff
        elif c == '{':
            try:
                j = pat.index('}', i)
            except ValueError:
                res += '\\{'
            else:
                stuff = pat[i:j]
                i = j+1
                res += '(%s)' % "|".join([shell_to_regex(p)[:-1] for p in stuff.split(",")])
        else:
            res += re.escape(c)
    return res + "$"

class ListItem(object):
    __slots__ = ("name", "active", "value")
    def __init__(self, s):
        a = s.split("\t")
        self.name = a.pop(0)
        self.active = int(a.pop(0))
        self.value = " ".join(a)
    def __str__(self):
        return "<%s %s %i %s>" % ( self.__class__, self.name, self.active, self.value )


################################################################################
#
# optparse Options subclass
#
################################################################################
import optparse

def check_diff_files(option, opt, value):
    if len(value) not in (1, 2, 3):
        raise optparse.OptionValueError(
            "option %s: invalid value: %r" % (opt, value))

def diff_files_callback(option, opt_str, value, parser):
    """Gather arguments after option in a list and append to option.dest."""
    assert value is None
    diff_files_args = []
    rargs = parser.rargs
    while rargs:
        arg = rargs[0]

        # Stop if we hit an arg like "--foo", "-a", "-fx", "--file=f",
        # etc.  Note that this also stops on "-3" or "-3.0", so if
        # your option takes numeric values, you will need to handle
        # this.
        if ((arg[:2] == "--" and len(arg) > 2) or
            (arg[:1] == "-" and len(arg) > 1 and arg[1] != "-")):
            break
        else:
            diff_files_args.append(arg)
            del rargs[0]

    value = getattr(parser.values, option.dest) or []
    value.append(diff_files_args)
    setattr(parser.values, option.dest, value)


class MeldOption(optparse.Option):
    """Custom Option which adds the 'diff_files' action."""
    TYPES = optparse.Option.TYPES + ("diff_files",)
    TYPE_CHECKER = copy.copy(optparse.Option.TYPE_CHECKER)
    TYPE_CHECKER["diff_files"] = check_diff_files

    ACTIONS = optparse.Option.ACTIONS + ("diff_files",)
    TYPED_ACTIONS = optparse.Option.TYPED_ACTIONS + ("diff_files",)

    def take_action(self, action, dest, opt, value, values, parser):
        if action == "diff_files":
            diff_files_callback(self, opt, value, parser)
        else:
            optparse.Option.take_action(
                self, action, dest, opt, value, values, parser)
