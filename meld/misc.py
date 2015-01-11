# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2009 Vincent Legoll <vincent.legoll@gmail.com>
# Copyright (C) 2012-2013 Kai Willadsen <kai.willadsen@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or (at
# your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Module of commonly used helper classes and functions
"""

import os
import errno
import shutil
import re
import subprocess

from gi.repository import Gtk

from meld.conf import _


if os.name != "nt":
    from select import select
else:
    import time

    def select(rlist, wlist, xlist, timeout):
        time.sleep(timeout)
        return rlist, wlist, xlist


def error_dialog(primary, secondary):
    """A common error dialog handler for Meld

    This should only ever be used as a last resort, and for errors that
    a user is unlikely to encounter. If you're tempted to use this,
    think twice.

    Primary must be plain text. Secondary must be valid markup.
    """
    return modal_dialog(
        primary, secondary, Gtk.ButtonsType.CLOSE, parent=None,
        messagetype=Gtk.MessageType.ERROR)


def modal_dialog(
        primary, secondary, buttons, parent=None,
        messagetype=Gtk.MessageType.WARNING):
    """A common message dialog handler for Meld

    This should only ever be used for interactions that must be resolved
    before the application flow can continue.

    Primary must be plain text. Secondary must be valid markup.
    """

    if not parent:
        from meld.meldapp import app
        parent = app.get_active_window()
    elif not isinstance(parent, Gtk.Window):
        parent = parent.get_toplevel()

    if isinstance(buttons, Gtk.ButtonsType):
        custom_buttons = []
    else:
        custom_buttons, buttons = buttons, Gtk.ButtonsType.NONE

    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        destroy_with_parent=True,
        message_type=messagetype,
        buttons=buttons,
        text=primary)
    dialog.format_secondary_markup(secondary)

    for label, response_id in custom_buttons:
        dialog.add_button(label, response_id)

    response = dialog.run()
    dialog.destroy()
    return response


# Taken from epiphany
def position_menu_under_widget(menu, widget):
    container = widget.get_ancestor(Gtk.Container)

    widget_width = widget.get_allocation().width
    menu_width = menu.get_allocation().width
    menu_height = menu.get_allocation().height

    screen = menu.get_screen()
    monitor_num = screen.get_monitor_at_window(widget.get_window())
    if monitor_num < 0:
        monitor_num = 0
    monitor = screen.get_monitor_geometry(monitor_num)

    unused, x, y = widget.get_window().get_origin()
    allocation = widget.get_allocation()
    if not widget.get_has_window():
        x += allocation.x
        y += allocation.y

    if container.get_direction() == Gtk.TextDirection.LTR:
        x += allocation.width - widget_width
    else:
        x += widget_width - menu_width

    if (y + allocation.height + menu_height) <= monitor.y + monitor.height:
        y += allocation.height
    elif (y - menu_height) >= monitor.y:
        y -= menu_height
    elif monitor.y + monitor.height - (y + allocation.height) > y:
        y += allocation.height
    else:
        y -= menu_height

    return (x, y, False)


def make_tool_button_widget(label):
    """Make a GtkToolButton label-widget suggestive of a menu dropdown"""
    arrow = Gtk.Arrow(
        arrow_type=Gtk.ArrowType.DOWN, shadow_type=Gtk.ShadowType.NONE)
    label = Gtk.Label(label=label)
    hbox = Gtk.HBox(spacing=3)
    hbox.pack_end(arrow, True, True, 0)
    hbox.pack_end(label, True, True, 0)
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
        if e.errno not in (errno.EPERM, errno.ENOTSUP):
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

    Based on fnmatch.translate().
    We also handle {a,b,c} where fnmatch does not.
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
                res += '(%s)' % "|".join(
                    [shell_to_regex(p)[:-1] for p in stuff.split(",")]
                )
        else:
            res += re.escape(c)
    return res + "$"
