### Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
### Copyright (C) 2009 Vincent Legoll <vincent.legoll@gmail.com>
### Copyright (C) 2012 Kai Willadsen <kai.willadsen@gmail.com>

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

"""Module of commonly used helper classes and functions
"""

import os
from gettext import gettext as _
import errno
import shutil
import re
import subprocess

import gio
import gobject
import gtk


whitespace_re = re.compile(r"\s")

if os.name != "nt":
    from select import select
else:
    import time

    def select(rlist, wlist, xlist, timeout):
        time.sleep(timeout)
        return rlist, wlist, xlist


def shelljoin( command ):
    def quote(s):
        return ((whitespace_re.search(s) is None) and s or ('"%s"' % s))
    return " ".join( [ quote(x) for x in command ] )

def run_dialog( text, parent=None, messagetype=gtk.MESSAGE_WARNING, buttonstype=gtk.BUTTONS_OK, extrabuttons=()):
    """Run a dialog with text 'text'.
       Extra buttons are passed as tuples of (button label, response id).
    """
    escaped = gobject.markup_escape_text(text)
    d = gtk.MessageDialog(None,
        gtk.DIALOG_DESTROY_WITH_PARENT,
        messagetype,
        buttonstype,
        '<span weight="bold" size="larger">%s</span>' % escaped)
    if parent and isinstance(parent, gtk.Window):
        d.set_transient_for(parent.widget.get_toplevel())
    for b,rid in extrabuttons:
        d.add_button(b, rid)
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
    try:
        gtk.show_uri(gtk.gdk.screen_get_default(), uri, timestamp)
    except gio.Error:
        if uri.startswith("http://"):
            import webbrowser
            webbrowser.open_new_tab(uri)
        else:
            # Unhandled URI
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

def gdk_to_cairo_color(color):
    return (color.red / 65535., color.green / 65535., color.blue / 65535.)

def all_equal(alist):
    """Return true if all members of the list are equal to the first.

    An empty list is considered to have all elements equal.
    """
    if len(alist):
        first = alist[0]
        for n in alist[1:]:
            if n != first:
                return 0
    return 1
    
def shorten_names(*names):
    """Remove redunant parts of a list of names (e.g. /tmp/foo{1,2} -> foo{1,2}
    """
    # TODO: Update for different path separators
    prefix = os.path.commonprefix(names)
    prefixslash = prefix.rfind("/") + 1

    names = [n[prefixslash:] for n in names]
    paths = [n.split("/") for n in names]

    try:
        basenames = [p[-1] for p in paths]
    except IndexError:
        pass
    else:
        if all_equal(basenames):
            def firstpart(alist):
                if len(alist) > 1:
                    return "[%s] " % alist[0]
                else:
                    return ""
            roots = [firstpart(p) for p in paths]
            base = basenames[0].strip()
            return [r + base for r in roots]
    # no common path. empty names get changed to "[None]"
    return [name or _("[None]") for name in basenames]


def read_pipe_iter(command, errorstream, yield_interval=0.1, workdir=None):
    """Read the output of a shell command iteratively.

    Each time 'callback_interval' seconds pass without reading any data,
    this function yields None.
    When all the data is read, the entire string is yielded.
    If 'workdir' is specified the command is run from that directory.
    """
    class sentinel(object):
        def __init__(self):
            self.proc = None

        def __del__(self):
            if self.proc:
                errorstream.error("killing '%s'\n" % command[0])
                self.proc.terminate()
                errorstream.error("killed (status was '%i')\n" %
                                  self.proc.wait())

        def __call__(self):
            self.proc = subprocess.Popen(command, cwd=workdir,
                                         stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE)
            self.proc.stdin.close()
            childout, childerr = self.proc.stdout, self.proc.stderr
            bits = []
            while len(bits) == 0 or bits[-1] != "":
                state = select([childout, childerr], [], [childout, childerr],
                               yield_interval)
                if len(state[0]) == 0:
                    if len(state[2]) == 0:
                        yield None
                    else:
                        raise Exception("Error reading pipe")
                if childout in state[0]:
                    try:
                        # get buffer size
                        bits.append(childout.read(4096))
                    except IOError:
                        # FIXME: ick need to fix
                        break
                if childerr in state[0]:
                    try:
                        # how many chars?
                        errorstream.error(childerr.read(1))
                    except IOError:
                        # FIXME: ick need to fix
                        break
            status = self.proc.wait()
            errorstream.error(childerr.read())
            self.proc = None
            if status:
                errorstream.error("Exit code: %i\n" % status)
            yield "".join(bits)
            yield status
    if workdir == "":
        workdir = None
    return sentinel()()


def write_pipe(command, text, error=None):
    """Write 'text' into a shell command and discard its stdout output.
    """
    proc = subprocess.Popen(command, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=error)
    proc.communicate(text)
    return proc.wait()

def commonprefix(dirs):
    """Given a list of pathnames, returns the longest common leading component.
    """
    if not dirs:
        return ''
    n = [d.split(os.sep) for d in dirs]
    prefix = n[0]
    for item in n:
        for i in range(len(prefix)):
            if prefix[:i+1] != item[:i+1]:
                prefix = prefix[:i]
                if i == 0:
                    return ''
                break
    return os.sep.join(prefix)

def copy2(src, dst):
    """Like shutil.copy2 but ignores chmod errors, and copies symlinks as links
    See [Bug 568000] Copying to NTFS fails
    """
    if os.path.isdir(dst):
        dst = os.path.join(dst, os.path.basename(src))

    if os.path.islink(src) and os.path.isfile(src):
        if os.path.lexists(dst):
            os.unlink(dst)
        os.symlink(os.readlink(src), dst)
    elif os.path.isfile(src):
        shutil.copyfile(src, dst)
    else:
        raise OSError("Not a file")

    try:
        shutil.copystat(src, dst)
    except OSError as e:
        if e.errno != errno.EPERM:
            raise

def copytree(src, dst):
    """Similar to shutil.copytree, but always copies symlinks and doesn't
    error out if the destination path already exists.
    """
    # If the source tree is a symlink, duplicate the link and we're done.
    if os.path.islink(src):
        os.symlink(os.readlink(src), dst)
        return

    try:
        os.mkdir(dst)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    names = os.listdir(src)
    for name in names:
        srcname = os.path.join(src, name)
        dstname = os.path.join(dst, name)
        if os.path.islink(srcname):
            os.symlink(os.readlink(srcname), dstname)
        elif os.path.isdir(srcname):
            copytree(srcname, dstname)
        else:
            copy2(srcname, dstname)

    try:
        shutil.copystat(src, dst)
    except OSError as e:
        if e.errno != errno.EPERM:
            raise

def shell_escape(glob_pat):
    # TODO: handle all cases
    assert not re.compile(r"[][*?]").findall(glob_pat)
    return glob_pat.replace('{', '[{]').replace('}', '[}]')

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
