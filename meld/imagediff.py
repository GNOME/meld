# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2009-2019 Kai Willadsen <kai.willadsen@gmail.com>
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

import copy
import functools
import logging
import math
from enum import Enum
from typing import Optional, Tuple, Type

from gi.repository import Gdk, Gio, GLib, GObject, Gtk, GtkSource

# TODO: Don't from-import whole modules
from meld import misc
from meld.conf import _
from meld.const import (
    NEWLINES,
    TEXT_FILTER_ACTION_FORMAT,
    ActionMode,
    ChunkAction,
    FileComparisonMode,
)
from meld.iohelpers import find_shared_parent_path, prompt_save_filename
from meld.melddoc import ComparisonState, MeldDoc, open_files_external
from meld.menuhelpers import replace_menu_section
from meld.misc import user_critical, with_focused_pane
from meld.recent import RecentType
from meld.settings import bind_settings, get_meld_settings
from meld.ui.util import (
    make_multiobject_property_action,
    map_widgets_into_lists,
)
from meld.undo import UndoSequence

log = logging.getLogger(__name__)


def with_scroll_lock(lock_attr):
    """Decorator for locking a callback based on an instance attribute

    This is used when scrolling panes. Since a scroll event in one pane
    causes us to set the scroll position in other panes, we need to
    stop these other panes re-scrolling the initial one.

    Unlike a threading-style lock, this decorator discards any calls
    that occur while the lock is held, rather than queuing them.

    :param lock_attr: The instance attribute used to lock access
    """
    def wrap(function):
        @functools.wraps(function)
        def wrap_function(locked, *args, **kwargs):
            force_locked = locked.props.lock_scrolling
            if getattr(locked, lock_attr, False) or force_locked:
                return

            try:
                setattr(locked, lock_attr, True)
                return function(locked, *args, **kwargs)
            finally:
                setattr(locked, lock_attr, False)
        return wrap_function
    return wrap


MASK_SHIFT, MASK_CTRL = 1, 2
PANE_LEFT, PANE_RIGHT = -1, +1


# ~ class CursorDetails:
    # ~ __slots__ = (
        # ~ "pane", "pos", "line", "chunk", "prev", "next",
        # ~ "prev_conflict", "next_conflict",
    # ~ )

    # ~ def __init__(self):
        # ~ for var in self.__slots__:
            # ~ setattr(self, var, None)


@Gtk.Template(resource_path='/org/gnome/meld/ui/imagediff.ui')
class ImageDiff(Gtk.VBox, MeldDoc):
    """Two or three way comparison of image files"""

    __gtype_name__ = "ImageDiff"

    close_signal = MeldDoc.close_signal
    create_diff_signal = MeldDoc.create_diff_signal
    file_changed_signal = MeldDoc.file_changed_signal
    label_changed = MeldDoc.label_changed
    move_diff = MeldDoc.move_diff
    tab_state_changed = MeldDoc.tab_state_changed

    # ~ __gsettings_bindings_view__ = (
        # ~ ('ignore-blank-lines', 'ignore-blank-lines'),
        # ~ ('show-overview-map', 'show-overview-map'),
        # ~ ('overview-map-style', 'overview-map-style'),
    # ~ )

    show_overview_map = GObject.Property(type=bool, default=True)
    overview_map_style = GObject.Property(type=str, default='chunkmap')

    image_main0 = Gtk.Template.Child()
    image_main1 = Gtk.Template.Child()

    keylookup = {
        Gdk.KEY_Shift_L: MASK_SHIFT,
        Gdk.KEY_Shift_R: MASK_SHIFT,
        Gdk.KEY_Control_L: MASK_CTRL,
        Gdk.KEY_Control_R: MASK_CTRL,
    }

    # Identifiers for MsgArea messages
    (MSG_SAME, MSG_SLOW_HIGHLIGHT, MSG_SYNCPOINTS) = list(range(3))
    # Transient messages that should be removed if any file in the
    # comparison gets reloaded.
    TRANSIENT_MESSAGES = {MSG_SAME, MSG_SLOW_HIGHLIGHT}

    action_mode = GObject.Property(
        type=int,
        nick='Action mode for chunk change actions',
        default=ActionMode.Replace,
    )

    lock_scrolling = GObject.Property(
        type=bool,
        nick='Lock scrolling of all panes',
        default=False,
    )

    def __init__(
        self,
        num_panes,
        *,
        comparison_mode: FileComparisonMode = FileComparisonMode.Compare,
    ):
        super().__init__()

        # FIXME:
        # This unimaginable hack exists because GObject (or GTK+?)
        # doesn't actually correctly chain init calls, even if they're
        # not to GObjects. As a workaround, we *should* just be able to
        # put our class first, but because of Gtk.Template we can't do
        # that if it's a GObject, because GObject doesn't support
        # multiple inheritance and we need to inherit from our Widget
        # parent to make Template work.
        MeldDoc.__init__(self)
        bind_settings(self)

        # ~ widget_lists = [
            # ~ "sourcemap", "file_save_button", "file_toolbar",
            # ~ "linkmap", "msgarea_mgr", "readonlytoggle",
            # ~ "scrolledwindow", "textview", "vbox",
            # ~ "dummy_toolbar_linkmap", "filelabel",
            # ~ "file_open_button", "statusbar",
            # ~ "actiongutter", "dummy_toolbar_actiongutter",
            # ~ "chunkmap",
        # ~ ]
        # ~ map_widgets_into_lists(self, widget_lists)

        widget_lists = [
            "image_main",
        ]
        map_widgets_into_lists(self, widget_lists)

        self.warned_bad_comparison = False
        self._keymask = 0
        self.meta = {}
        self.lines_removed = 0
        self.focus_pane = None
        meld_settings = get_meld_settings()

        # ~ for (i, w) in enumerate(self.scrolledwindow):
            # ~ w.get_vadjustment().connect("value-changed", self._sync_vscroll, i)
            # ~ w.get_hadjustment().connect("value-changed", self._sync_hscroll)
        self._sync_vscroll_lock = False
        self._sync_hscroll_lock = False

        # ~ prop_action_group = Gio.SimpleActionGroup()
        # ~ for prop in sourceview_prop_actions:
            # ~ action = make_multiobject_property_action(self.textview, prop)
            # ~ prop_action_group.add_action(action)
        # ~ self.insert_action_group('view-local', prop_action_group)

        # Set up per-view action group for top-level menu insertion
        self.view_action_group = Gio.SimpleActionGroup()

        property_actions = (
            ('show-overview-map', self, 'show-overview-map'),
            ('lock-scrolling', self, 'lock_scrolling'),
        )
        for action_name, obj, prop_name in property_actions:
            action = Gio.PropertyAction.new(action_name, obj, prop_name)
            self.view_action_group.add_action(action)

        # Manually handle GAction additions
        # ~ actions = (
            # ~ ('copy', self.action_copy),
            # ~ ('copy-full-path', self.action_copy_full_path),
            # ~ ('next-pane', self.action_next_pane),
            # ~ ('open-external', self.action_open_external),
            # ~ ('open-folder', self.action_open_folder),
            # ~ ('previous-pane', self.action_prev_pane),
            # ~ ('refresh', self.action_refresh),
            # ~ ('swap-2-panes', self.action_swap),
        # ~ )
        # ~ for name, callback in actions:
            # ~ action = Gio.SimpleAction.new(name, None)
            # ~ action.connect('activate', callback)
            # ~ self.view_action_group.add_action(action)

        # ~ builder = Gtk.Builder.new_from_resource(
            # ~ '/org/gnome/meld/ui/imagediff-menus.ui')
        # ~ self.popup_menu_model = builder.get_object('imagediff-context-menu')
        # ~ self.popup_menu = Gtk.Menu.new_from_model(self.popup_menu_model)
        # ~ self.popup_menu.attach_to_widget(self)

        builder = Gtk.Builder.new_from_resource(
            '/org/gnome/meld/ui/imagediff-actions.ui')
        self.toolbar_actions = builder.get_object('view-toolbar')
        self.copy_action_button = builder.get_object('copy_action_button')

        self.set_num_panes(num_panes)

    def do_realize(self):
        Gtk.VBox().do_realize(self)

        builder = Gtk.Builder.new_from_resource(
            '/org/gnome/meld/ui/imagediff-menus.ui')
        # ~ filter_menu = builder.get_object('file-copy-actions-menu')

        # ~ self.copy_action_button.set_popover(
            # ~ Gtk.Popover.new_from_model(self.copy_action_button, filter_menu))

    def set_files(self, gfiles, encodings=None):
        """Load the given files

        If an element is None, the text of a pane is left as is.
        """
        # Debug.
        # ~ print ("MVZ: Setting files....")
        # ~ print ("gfiles:", gfiles)
        # ~ print ("self.num_panes:", self.num_panes)

        if len(gfiles) != self.num_panes:
            return

        encodings = encodings or ((None,) * len(gfiles))

        files = []
        for pane, (gfile, encoding) in enumerate(zip(gfiles, encodings)):
            if gfile:
                files.append((pane, gfile, encoding))
            # ~ else:
                # ~ self.textbuffer[pane].data.loaded = True

        # ~ if not files:
            # ~ self.scheduler.add_task(self._compare_files_internal())

        for pane, gfile, encoding in files:
            self.load_file_in_pane(pane, gfile, encoding)

    def load_file_in_pane(
            self,
            pane: int,
            gfile: Gio.File,
            encoding: GtkSource.Encoding = None):
        """Load a file into the given pane

        Don't call this directly; use `set_file()` or `set_files()`,
        which handle sensitivity and signal connection. Even if you
        don't care about those things, you need it because they'll be
        unconditionally added after file load, which will cause
        duplicate handlers, etc. if you don't do this thing.
        """

        # ~ print ("MVZ: Loading in pane....")
        # ~ print ("self.image_main:", self.image_main)
        # ~ self.image_main[pane].props.file = gfile
        # ~ self.image_main[pane].set_from_file(gfile) # Causes error...
        self.image_main[pane].set_from_file( gfile.get_path() )

        # ~ self.msgarea_mgr[pane].clear()

        # ~ buf = self.textbuffer[pane]
        # ~ buf.data.reset(gfile)
        # ~ self.file_open_button[pane].props.file = gfile

        # FIXME: this was self.textbuffer[pane].data.label, which could be
        # either a custom label or the fallback
        # ~ self.filelabel[pane].props.gfile = gfile

        # ~ if buf.data.is_special:
            # ~ loader = GtkSource.FileLoader.new_from_stream(
                # ~ buf, buf.data.sourcefile, buf.data.gfile.read())
        # ~ else:
            # ~ loader = GtkSource.FileLoader.new(buf, buf.data.sourcefile)

        # ~ custom_candidates = get_custom_encoding_candidates()
        # ~ if encoding:
            # ~ custom_candidates = [encoding]
        # ~ if custom_candidates:
            # ~ loader.set_candidate_encodings(custom_candidates)

        # ~ loader.load_async(
            # ~ GLib.PRIORITY_HIGH,
            # ~ callback=self.file_loaded,
            # ~ user_data=(pane,)
        # ~ )

    def set_num_panes(self, n):
        if n == self.num_panes or n not in (1, 2, 3):
            return

        self.num_panes = n


    def on_delete_event(self):
        self.state = ComparisonState.Closing
        self.close_signal.emit(0)
        return Gtk.ResponseType.OK
