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

import collections
import os
import errno
import shutil
import re
import subprocess

from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import GtkSource

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
def position_menu_under_widget(menu, x, y, widget):
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


def get_base_style_scheme():
    MELD_STYLE_SCHEME = "meld-base"
    MELD_STYLE_SCHEME_DARK = "meld-dark"

    global base_style_scheme

    if base_style_scheme:
        return base_style_scheme

    env_theme = GLib.getenv('GTK_THEME')
    if env_theme:
        use_dark = env_theme.endswith(':dark')
    else:
        gtk_settings = Gtk.Settings.get_default()
        use_dark = gtk_settings.props.gtk_application_prefer_dark_theme
    base_scheme_name = (
        MELD_STYLE_SCHEME_DARK if use_dark else MELD_STYLE_SCHEME)

    manager = GtkSource.StyleSchemeManager.get_default()
    base_style_scheme = manager.get_scheme(base_scheme_name)

    return base_style_scheme

base_style_scheme = None


def parse_rgba(string):
    """Parse a string to a Gdk.RGBA across different GTK+ APIs

    Introspection changes broke this API in GTK+ 3.20; this function
    is just a backwards-compatiblity workaround.
    """
    colour = Gdk.RGBA()
    result = colour.parse(string)
    return result[1] if isinstance(result, tuple) else colour


def colour_lookup_with_fallback(name, attribute):
    from meld.settings import meldsettings
    source_style = meldsettings.style_scheme

    style = source_style.get_style(name)
    style_attr = getattr(style.props, attribute) if style else None
    if not style or not style_attr:
        base_style = get_base_style_scheme()
        try:
            style = base_style.get_style(name)
            style_attr = getattr(style.props, attribute)
        except AttributeError:
            pass

    if not style_attr:
        import sys
        print >> sys.stderr, _(
            "Couldn't find colour scheme details for %s-%s; "
            "this is a bad install") % (name, attribute)
        sys.exit(1)

    return parse_rgba(style_attr)


def get_common_theme():
    lookup = colour_lookup_with_fallback
    fill_colours = {
        "insert": lookup("meld:insert", "background"),
        "delete": lookup("meld:insert", "background"),
        "conflict": lookup("meld:conflict", "background"),
        "replace": lookup("meld:replace", "background"),
        "current-chunk-highlight": lookup(
            "meld:current-chunk-highlight", "background")
    }
    line_colours = {
        "insert": lookup("meld:insert", "line-background"),
        "delete": lookup("meld:insert", "line-background"),
        "conflict": lookup("meld:conflict", "line-background"),
        "replace": lookup("meld:replace", "line-background"),
    }
    return fill_colours, line_colours


def gdk_to_cairo_color(color):
    return (color.red / 65535., color.green / 65535., color.blue / 65535.)


def fallback_decode(bytes, encodings, lossy=False):
    """Try and decode bytes according to multiple encodings

    Generally, this should be used for best-effort decoding, when the
    desired behaviour is "probably this, or UTF-8".

    If lossy is True, then decode errors will be replaced. This may be
    reasonable when the string is for display only.
    """
    if isinstance(bytes, unicode):
        return bytes

    for encoding in encodings:
        try:
            return bytes.decode(encoding)
        except UnicodeDecodeError:
            pass

    if lossy:
        return bytes.decode(encoding, errors='replace')

    raise ValueError(
        "Couldn't decode %r as one of %r" % (bytes, encodings))


def all_same(lst):
    """Return True if all elements of the list are equal"""
    return not lst or lst.count(lst[0]) == len(lst)


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
        if all_same(basenames):
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


def read_pipe_iter(command, workdir, errorstream, yield_interval=0.1):
    """Read the output of a shell command iteratively.

    Each time 'callback_interval' seconds pass without reading any data,
    this function yields None.
    When all the data is read, the entire string is yielded.
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
            yield status, "".join(bits)
    return sentinel()()


def write_pipe(command, text, error=None):
    """Write 'text' into a shell command and discard its stdout output.
    """
    proc = subprocess.Popen(command, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=error)
    proc.communicate(text)
    return proc.wait()


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
                i = j + 1
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
                i = j + 1
                res += '(%s)' % "|".join(
                    [shell_to_regex(p)[:-1] for p in stuff.split(",")]
                )
        else:
            res += re.escape(c)
    return res + "$"


def merge_intervals(interval_list):
    """Merge a list of intervals

    Returns a list of itervals as 2-tuples with all overlapping
    intervals merged.

    interval_list must be a list of 2-tuples of integers representing
    the start and end of an interval.
    """

    if len(interval_list) < 2:
        return interval_list

    interval_list = collections.deque(sorted(interval_list))
    merged_intervals = [interval_list.popleft()]
    current_start, current_end = merged_intervals[-1]

    while interval_list:
        new_start, new_end = interval_list.popleft()

        if current_end >= new_end:
            continue

        if current_end < new_start:
            # Intervals do not overlap; create a new one
            merged_intervals.append((new_start, new_end))
        elif current_end < new_end:
            # Intervals overlap; extend the current one
            merged_intervals[-1] = (current_start, new_end)

        current_start, current_end = merged_intervals[-1]

    return merged_intervals


def apply_text_filters(txt, regexes, apply_fn=None):
    """Apply text filters

    Text filters "regexes", resolved as regular expressions are applied
    to "txt".

    "apply_fn" is a callable run for each filtered interval
    """
    filter_ranges = []
    for r in regexes:
        for match in r.finditer(txt):

            # If there are no groups in the match, use the whole match
            if not r.groups:
                span = match.span()
                if span[0] != span[1]:
                    filter_ranges.append(span)
                continue

            # If there are groups in the regex, include all groups that
            # participated in the match
            for i in range(r.groups):
                span = match.span(i + 1)
                if span != (-1, -1) and span[0] != span[1]:
                    filter_ranges.append(span)

    filter_ranges = merge_intervals(filter_ranges)

    if apply_fn:
        for (start, end) in reversed(filter_ranges):
            apply_fn(start, end)

    offset = 0
    result_txts = []
    for (start, end) in filter_ranges:
        assert txt[start:end].count("\n") == 0
        result_txts.append(txt[offset:start])
        offset = end
    result_txts.append(txt[offset:])
    return "".join(result_txts)
