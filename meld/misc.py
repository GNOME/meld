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
import errno
import functools
import os
import shutil
import subprocess
from pathlib import PurePath
from typing import (
    AnyStr,
    Callable,
    List,
    Generator,
    Union,
    Mapping,
    Optional,
    Pattern,
    Sequence,
    Tuple,
    TYPE_CHECKING,
)

from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import Gtk
from gi.repository import GtkSource

from meld.conf import _

if TYPE_CHECKING:
    from meld.vcview import ConsoleStream


if os.name != "nt":
    from select import select
else:
    import time

    def select(rlist, wlist, xlist, timeout):
        time.sleep(timeout)
        return rlist, wlist, xlist


def with_focused_pane(function):
    @functools.wraps(function)
    def wrap_function(*args, **kwargs):
        pane = args[0]._get_focused_pane()
        if pane == -1:
            return
        return function(args[0], pane, *args[1:], **kwargs)
    return wrap_function


def get_modal_parent(widget: Optional[Gtk.Widget] = None) -> Gtk.Window:
    parent: Gtk.Window
    if not widget:
        from meld.meldapp import app
        parent = app.get_active_window()
    elif not isinstance(widget, Gtk.Window):
        parent = widget.get_toplevel()
    else:
        parent = widget
    return parent


def error_dialog(primary: str, secondary: str) -> Gtk.ResponseType:
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
            primary: str,
            secondary: str,
            buttons: Union[Gtk.ButtonsType, Sequence[Tuple[str, int]]],
            parent: Optional[Gtk.Window] = None,
            messagetype: Gtk.MessageType = Gtk.MessageType.WARNING
        ) -> Gtk.ResponseType:
    """A common message dialog handler for Meld

    This should only ever be used for interactions that must be resolved
    before the application flow can continue.

    Primary must be plain text. Secondary must be valid markup.
    """

    custom_buttons: Sequence[Tuple[str, int]] = []
    if not isinstance(buttons, Gtk.ButtonsType):
        custom_buttons, buttons = buttons, Gtk.ButtonsType.NONE

    dialog = Gtk.MessageDialog(
        transient_for=get_modal_parent(parent),
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


def user_critical(
        primary: str, message: str) -> Callable[[Callable], Callable]:
    """Decorator for when the user must be told about failures

    The use case here is for e.g., saving a file, where even if we
    don't handle errors, the user *still* needs to know that something
    failed. This should be extremely sparingly used, but anything where
    the user might not otherwise see a problem and data loss is a
    potential side effect should be considered a candidate.
    """

    def wrap(function):
        @functools.wraps(function)
        def wrap_function(locked, *args, **kwargs):
            try:
                return function(locked, *args, **kwargs)
            except Exception:
                error_dialog(
                    primary=primary,
                    secondary=_(
                        "{}\n\n"
                        "Meld encountered a critical error while running:\n"
                        "<tt>{}</tt>").format(
                            message, GLib.markup_escape_text(str(function))
                    ),
                )
                raise
        return wrap_function
    return wrap


def make_tool_button_widget(label_text: str) -> Gtk.HBox:
    """Make a GtkToolButton label-widget suggestive of a menu dropdown"""
    arrow = Gtk.Arrow(
        arrow_type=Gtk.ArrowType.DOWN, shadow_type=Gtk.ShadowType.NONE)
    label = Gtk.Label(label=label_text)
    hbox = Gtk.HBox(spacing=3)
    hbox.pack_end(arrow, True, True, 0)
    hbox.pack_end(label, True, True, 0)
    hbox.show_all()
    return hbox


MELD_STYLE_SCHEME = "meld-base"
MELD_STYLE_SCHEME_DARK = "meld-dark"


base_style_scheme: Optional[GtkSource.StyleScheme] = None


def get_base_style_scheme() -> GtkSource.StyleScheme:

    global base_style_scheme

    if base_style_scheme:
        return base_style_scheme

    env_theme = GLib.getenv('GTK_THEME')
    if env_theme:
        use_dark = env_theme.endswith(':dark')
    else:
        gtk_settings = Gtk.Settings.get_default()
        use_dark = gtk_settings.props.gtk_application_prefer_dark_theme

    # As of 3.28, the global dark theme switch is going away.
    if not use_dark:
        from meld.sourceview import MeldSourceView
        stylecontext = MeldSourceView().get_style_context()
        background_set, rgba = (
            stylecontext.lookup_color('theme_bg_color'))

        # This heuristic is absolutely dire. I made it up. There's
        # literally no basis to this.
        if background_set and rgba.red + rgba.green + rgba.blue < 1.0:
            use_dark = True

    base_scheme_name = (
        MELD_STYLE_SCHEME_DARK if use_dark else MELD_STYLE_SCHEME)

    manager = GtkSource.StyleSchemeManager.get_default()
    base_style_scheme = manager.get_scheme(base_scheme_name)

    return base_style_scheme


def colour_lookup_with_fallback(name: str, attribute: str) -> Gdk.RGBA:
    from meld.settings import meldsettings
    source_style = meldsettings.style_scheme

    style = source_style.get_style(name) if source_style else None
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
        print(_(
            "Couldn’t find colour scheme details for %s-%s; "
            "this is a bad install") % (name, attribute), file=sys.stderr)
        sys.exit(1)

    colour = Gdk.RGBA()
    colour.parse(style_attr)
    return colour


def get_common_theme() -> Tuple[Mapping[str, Gdk.RGBA], Mapping[str, Gdk.RGBA]]:
    lookup = colour_lookup_with_fallback
    fill_colours = {
        "insert": lookup("meld:insert", "background"),
        "delete": lookup("meld:insert", "background"),
        "conflict": lookup("meld:conflict", "background"),
        "replace": lookup("meld:replace", "background"),
        "error": lookup("meld:error", "background"),
        "focus-highlight": lookup("meld:current-line-highlight", "foreground"),
        "current-chunk-highlight": lookup(
            "meld:current-chunk-highlight", "background")
    }
    line_colours = {
        "insert": lookup("meld:insert", "line-background"),
        "delete": lookup("meld:insert", "line-background"),
        "conflict": lookup("meld:conflict", "line-background"),
        "replace": lookup("meld:replace", "line-background"),
        "error": lookup("meld:error", "line-background"),
    }
    return fill_colours, line_colours


def all_same(iterable: Sequence) -> bool:
    """Return True if all elements of the list are equal"""
    sample, has_no_sample = None, True
    for item in iterable or ():
        if has_no_sample:
            sample, has_no_sample = item, False
        elif sample != item:
            return False
    return True


def shorten_names(*names: str) -> List[str]:
    """Remove common parts of a list of paths

    For example, `('/tmp/foo1', '/tmp/foo2')` would be summarised as
    `('foo1', 'foo2')`. Paths that share a basename are distinguished
    by prepending an indicator, e.g., `('/a/b/c', '/a/d/c')` would be
    summarised to `['[b] c', '[d] c']`.
    """

    paths = [PurePath(n) for n in names]

    # Identify the longest common path among the list of path
    common = set(paths[0].parents)
    common = common.intersection(*(p.parents for p in paths))
    if not common:
        return list(names)
    common_parent = sorted(common, key=lambda p: -len(p.parts))[0]

    paths = [p.relative_to(common_parent) for p in paths]
    basenames = [p.name for p in paths]

    if all_same(basenames):
        def firstpart(path: PurePath) -> str:
            if len(path.parts) > 1 and path.parts[0]:
                return "[%s] " % path.parts[0]
            else:
                return ""
        return [firstpart(p) + p.name for p in paths]

    return [name or _("[None]") for name in basenames]


SubprocessGenerator = Generator[Union[Tuple[int, str], None], None, None]


def read_pipe_iter(
            command: List[str],
            workdir: str,
            errorstream: 'ConsoleStream',
            yield_interval: float = 0.1,
        ) -> SubprocessGenerator:
    """Read the output of a shell command iteratively.

    Each time 'callback_interval' seconds pass without reading any data,
    this function yields None.
    When all the data is read, the entire string is yielded.
    """
    class Sentinel:

        proc: Optional[subprocess.Popen]

        def __init__(self) -> None:
            self.proc = None

        def __del__(self) -> None:
            if self.proc:
                errorstream.error("killing '%s'\n" % command[0])
                self.proc.terminate()
                errorstream.error("killed (status was '%i')\n" %
                                  self.proc.wait())

        def __call__(self) -> SubprocessGenerator:
            self.proc = subprocess.Popen(
                command, cwd=workdir, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True)
            self.proc.stdin.close()
            childout, childerr = self.proc.stdout, self.proc.stderr
            bits: List[str] = []
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

    return Sentinel()()


def write_pipe(
        command: List[str], text: str, error: Optional[int] = None) -> int:
    """Write 'text' into a shell command and discard its stdout output.
    """
    proc = subprocess.Popen(command, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=error)
    proc.communicate(text)
    return proc.wait()


def copy2(src: str, dst: str) -> None:
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


def copytree(src: str, dst: str) -> None:
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


def merge_intervals(
        interval_list: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Merge a list of intervals

    Returns a list of itervals as 2-tuples with all overlapping
    intervals merged.

    interval_list must be a list of 2-tuples of integers representing
    the start and end of an interval.
    """

    if len(interval_list) < 2:
        return interval_list

    interval_deque = collections.deque(sorted(interval_list))
    merged_intervals = [interval_deque.popleft()]
    current_start, current_end = merged_intervals[-1]

    while interval_deque:
        new_start, new_end = interval_deque.popleft()

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


def apply_text_filters(
            txt: AnyStr,
            regexes: Sequence[Pattern],
            apply_fn: Optional[Callable[[int, int], None]] = None
        ) -> AnyStr:
    """Apply text filters

    Text filters "regexes", resolved as regular expressions are applied
    to "txt". "txt" may be either strings or bytes, but the supplied
    regexes must match the type.

    "apply_fn" is a callable run for each filtered interval
    """
    empty_string = b"" if isinstance(txt, bytes) else ""
    newline = b"\n" if isinstance(txt, bytes) else "\n"

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
        assert txt[start:end].count(newline) == 0
        result_txts.append(txt[offset:start])
        offset = end
    result_txts.append(txt[offset:])
    return empty_string.join(result_txts)


def calc_syncpoint(adj: Gtk.Adjustment) -> float:
    """Calculate a cross-pane adjustment synchronisation point

    Our normal syncpoint is the middle of the screen. If the
    current position is within the first half screen of a
    document, we scale the sync point linearly back to 0.0 (top
    of the screen); if it's the the last half screen, we again
    scale linearly to 1.0.

    The overall effect of this is to make sure that the top and
    bottom parts of documents with different lengths and chunk
    offsets correctly scroll into view.
    """

    current = adj.get_value()
    half_a_screen = adj.get_page_size() / 2

    syncpoint = 0.0
    # How far through the first half-screen our adjustment is
    top_val = adj.get_lower()
    first_scale = (current - top_val) / half_a_screen
    syncpoint += 0.5 * min(1, first_scale)
    # How far through the last half-screen our adjustment is
    bottom_val = adj.get_upper() - 1.5 * adj.get_page_size()
    last_scale = (current - bottom_val) / half_a_screen
    syncpoint += 0.5 * max(0, last_scale)
    return syncpoint
