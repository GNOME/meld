# coding=UTF-8

# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2009-2013 Kai Willadsen <kai.willadsen@gmail.com>
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

import collections
import copy
import datetime
import errno
import functools
import locale
import os
import re
import shutil
import stat
import sys

from gi.repository import GLib
from gi.repository import Gio
from gi.repository import GObject
from gi.repository import Gdk
from gi.repository import Gtk

from . import melddoc
from . import tree
from . import misc
from . import recent
from .ui import gnomeglade
from .ui import emblemcellrenderer

from collections import namedtuple
from decimal import Decimal

from meld.conf import _
from meld.misc import all_same
from meld.settings import bind_settings, meldsettings, settings


################################################################################
#
# Local Functions
#
################################################################################

class StatItem(namedtuple('StatItem', 'mode size time')):
    __slots__ = ()

    @classmethod
    def _make(cls, stat_result):
        return StatItem(stat.S_IFMT(stat_result.st_mode),
                        stat_result.st_size, stat_result.st_mtime)

    def shallow_equal(self, other, time_resolution_ns):
        if self.size != other.size:
            return False

        # Shortcut to avoid expensive Decimal calculations. 2 seconds is our
        # current accuracy threshold (for VFAT), so should be safe for now.
        if abs(self.time - other.time) > 2:
            return False

        dectime1 = Decimal(self.time).scaleb(Decimal(9)).quantize(1)
        dectime2 = Decimal(other.time).scaleb(Decimal(9)).quantize(1)
        mtime1 = dectime1 // time_resolution_ns
        mtime2 = dectime2 // time_resolution_ns

        return mtime1 == mtime2


CacheResult = namedtuple('CacheResult', 'stats result')


_cache = {}
Same, SameFiltered, DodgySame, DodgyDifferent, Different, FileError = \
    list(range(6))
# TODO: Get the block size from os.stat
CHUNK_SIZE = 4096


def remove_blank_lines(text):
    splits = text.splitlines()
    lines = text.splitlines(True)
    blanks = set([i for i, l in enumerate(splits) if not l])
    lines = [l for i, l in enumerate(lines) if i not in blanks]
    return ''.join(lines)


def _files_same(files, regexes, comparison_args):
    """Determine whether a list of files are the same.

    Possible results are:
      Same: The files are the same
      SameFiltered: The files are identical only after filtering with 'regexes'
      DodgySame: The files are superficially the same (i.e., type, size, mtime)
      DodgyDifferent: The files are superficially different
      FileError: There was a problem reading one or more of the files
    """

    if all_same(files):
        return Same

    files = tuple(files)
    regexes = tuple(regexes)
    stats = tuple([StatItem._make(os.stat(f)) for f in files])

    shallow_comparison = comparison_args['shallow-comparison']
    time_resolution_ns = comparison_args['time-resolution']
    ignore_blank_lines = comparison_args['ignore_blank_lines']

    need_contents = comparison_args['apply-text-filters']

    # If all entries are directories, they are considered to be the same
    if all([stat.S_ISDIR(s.mode) for s in stats]):
        return Same

    # If any entries are not regular files, consider them different
    if not all([stat.S_ISREG(s.mode) for s in stats]):
        return Different

    # Compare files superficially if the options tells us to
    if shallow_comparison:
        if all(s.shallow_equal(stats[0], time_resolution_ns) for s in stats[1:]):
            return DodgySame
        else:
            return Different

    # If there are no text filters, unequal sizes imply a difference
    if not need_contents and not all_same([s.size for s in stats]):
        return Different

    # Check the cache before doing the expensive comparison
    cache_key = (files, need_contents, regexes, ignore_blank_lines)
    cache = _cache.get(cache_key)
    if cache and cache.stats == stats:
        return cache.result

    # Open files and compare bit-by-bit
    contents = [[] for f in files]
    result = None

    try:
        handles = [open(f, "rb") for f in files]
        try:
            data = [h.read(CHUNK_SIZE) for h in handles]

            # Rough test to see whether files are binary. If files are guessed
            # to be binary, we don't examine contents for speed and space.
            if any(["\0" in d for d in data]):
                need_contents = False

            while True:
                if all_same(data):
                    if not data[0]:
                        break
                else:
                    result = Different
                    if not need_contents:
                        break

                if need_contents:
                    for i in range(len(data)):
                        contents[i].append(data[i])

                data = [h.read(CHUNK_SIZE) for h in handles]

        # Files are too large; we can't apply filters
        except (MemoryError, OverflowError):
            result = DodgySame if all_same(stats) else DodgyDifferent
        finally:
            for h in handles:
                h.close()
    except IOError:
        # Don't cache generic errors as results
        return FileError

    if result is None:
        result = Same

    if result == Different and need_contents:
        contents = ["".join(c) for c in contents]
        # For probable text files, discard newline differences to match
        # file comparisons.
        contents = ["\n".join(c.splitlines()) for c in contents]

        contents = [misc.apply_text_filters(c, regexes) for c in contents]

        if ignore_blank_lines:
            contents = [remove_blank_lines(c) for c in contents]
        result = SameFiltered if all_same(contents) else Different

    _cache[cache_key] = CacheResult(stats, result)
    return result


COL_EMBLEM, COL_SIZE, COL_TIME, COL_PERMS, COL_END = \
        range(tree.COL_END, tree.COL_END + 5)


class DirDiffTreeStore(tree.DiffTreeStore):
    def __init__(self, ntree):
        tree.DiffTreeStore.__init__(self, ntree, [str, str, str, str])


class CanonicalListing(object):
    """Multi-pane lists with canonicalised matching and error detection"""

    def __init__(self, n, canonicalize=None):
        self.items = collections.defaultdict(lambda: [None] * n)
        self.errors = []
        if canonicalize is not None:
            self.canonicalize = canonicalize
            self.add = self.add_canon

    def add(self, pane, item):
        self.items[item][pane] = item

    def add_canon(self, pane, item):
        ci = self.canonicalize(item)
        if self.items[ci][pane] is None:
            self.items[ci][pane] = item
        else:
            self.errors.append((pane, item, self.items[ci][pane]))

    def get(self):
        first = lambda seq: next(s for s in seq if s)
        filled = lambda seq: tuple([s or first(seq) for s in seq])
        return sorted(filled(v) for v in self.items.values())


################################################################################
#
# DirDiff
#
################################################################################

class DirDiff(melddoc.MeldDoc, gnomeglade.Component):
    """Two or three way folder comparison"""

    __gtype_name__ = "DirDiff"

    __gsettings_bindings__ = (
        ('folder-ignore-symlinks', 'ignore-symlinks'),
        ('folder-shallow-comparison', 'shallow-comparison'),
        ('folder-time-resolution', 'time-resolution'),
        ('folder-status-filters', 'status-filters'),
        ('folder-filter-text', 'apply-text-filters'),
        ('ignore-blank-lines', 'ignore-blank-lines'),
    )

    apply_text_filters = GObject.property(
        type=bool,
        nick="Apply text filters",
        blurb=(
            "Whether text filters and other text sanitisation preferences "
            "should be applied when comparing file contents"),
        default=False,
    )
    ignore_blank_lines = GObject.property(
        type=bool,
        nick="Ignore blank lines",
        blurb="Whether to ignore blank lines when comparing file contents",
        default=False,
    )
    ignore_symlinks = GObject.property(
        type=bool,
        nick="Ignore symbolic links",
        blurb="Whether to follow symbolic links when comparing folders",
        default=False,
    )
    shallow_comparison = GObject.property(
        type=bool,
        nick="Use shallow comparison",
        blurb="Whether to compare files based solely on size and mtime",
        default=False,
    )
    status_filters = GObject.property(
        type=GObject.TYPE_STRV,
        nick="File status filters",
        blurb="Files with these statuses will be shown by the comparison.",
    )
    time_resolution = GObject.property(
        type=int,
        nick="Time resolution",
        blurb="When comparing based on mtime, the minimum difference in "
              "nanoseconds between two files before they're considered to "
              "have different mtimes.",
        default=100,
    )

    """Dictionary mapping tree states to corresponding difflib-like terms"""
    chunk_type_map = {
        tree.STATE_NORMAL: None,
        tree.STATE_NOCHANGE: None,
        tree.STATE_NEW: "insert",
        tree.STATE_ERROR: "error",
        tree.STATE_EMPTY: None,
        tree.STATE_MODIFIED: "replace",
        tree.STATE_MISSING: "delete",
        tree.STATE_NONEXIST: "delete",
    }

    state_actions = {
        tree.STATE_NORMAL: ("normal", "ShowSame"),
        tree.STATE_NEW: ("new", "ShowNew"),
        tree.STATE_MODIFIED: ("modified", "ShowModified"),
    }

    def __init__(self, num_panes):
        melddoc.MeldDoc.__init__(self)
        gnomeglade.Component.__init__(self, "dirdiff.ui", "dirdiff",
                                      ["DirdiffActions"])
        bind_settings(self)

        self.ui_file = gnomeglade.ui_file("dirdiff-ui.xml")
        self.actiongroup = self.DirdiffActions
        self.actiongroup.set_translation_domain("meld")

        self.name_filters = []
        self.text_filters = []
        self.create_name_filters()
        self.create_text_filters()
        self.settings_handlers = [
            meldsettings.connect("file-filters-changed",
                                 self.on_file_filters_changed),
            meldsettings.connect("text-filters-changed",
                                 self.on_text_filters_changed)
        ]

        self.map_widgets_into_lists(["treeview", "fileentry", "scrolledwindow",
                                     "diffmap", "linkmap", "msgarea_mgr",
                                     "vbox", "dummy_toolbar_linkmap",
                                     "file_toolbar"])

        self.widget.ensure_style()

        self.custom_labels = []
        self.set_num_panes(num_panes)

        self.widget.connect("style-updated", self.model.on_style_updated)
        self.model.on_style_updated(self.widget)

        self.do_to_others_lock = False
        self.focus_in_events = []
        self.focus_out_events = []
        for treeview in self.treeview:
            handler_id = treeview.connect("focus-in-event", self.on_treeview_focus_in_event)
            self.focus_in_events.append(handler_id)
            handler_id = treeview.connect("focus-out-event", self.on_treeview_focus_out_event)
            self.focus_out_events.append(handler_id)
            treeview.set_search_equal_func(self.model.treeview_search_cb, None)
        self.current_path, self.prev_path, self.next_path = None, None, None
        self.on_treeview_focus_out_event(None, None)
        self.focus_pane = None
        self.row_expansions = set()

        # One column-dict for each treeview, for changing visibility and order
        self.columns_dict = [{}, {}, {}]
        for i in range(3):
            col_index = self.model.column_index
            # Create icon and filename CellRenderer
            column = Gtk.TreeViewColumn(_("Name"))
            column.set_resizable(True)
            rentext = Gtk.CellRendererText()
            renicon = emblemcellrenderer.EmblemCellRenderer()
            column.pack_start(renicon, False)
            column.pack_start(rentext, True)
            column.set_attributes(rentext, markup=col_index(tree.COL_TEXT, i),
                                  foreground_rgba=col_index(tree.COL_FG, i),
                                  style=col_index(tree.COL_STYLE, i),
                                  weight=col_index(tree.COL_WEIGHT, i),
                                  strikethrough=col_index(tree.COL_STRIKE, i))
            column.set_attributes(renicon,
                                  icon_name=col_index(tree.COL_ICON, i),
                                  emblem_name=col_index(COL_EMBLEM, i),
                                  icon_tint=col_index(tree.COL_TINT, i))
            self.treeview[i].append_column(column)
            self.columns_dict[i]["name"] = column
            # Create file size CellRenderer
            column = Gtk.TreeViewColumn(_("Size"))
            column.set_resizable(True)
            rentext = Gtk.CellRendererText()
            column.pack_start(rentext, True)
            column.set_attributes(rentext, markup=col_index(COL_SIZE, i))
            self.treeview[i].append_column(column)
            self.columns_dict[i]["size"] = column
            # Create date-time CellRenderer
            column = Gtk.TreeViewColumn(_("Modification time"))
            column.set_resizable(True)
            rentext = Gtk.CellRendererText()
            column.pack_start(rentext, True)
            column.set_attributes(rentext, markup=col_index(COL_TIME, i))
            self.treeview[i].append_column(column)
            self.columns_dict[i]["modification time"] = column
            # Create permissions CellRenderer
            column = Gtk.TreeViewColumn(_("Permissions"))
            column.set_resizable(True)
            rentext = Gtk.CellRendererText()
            column.pack_start(rentext, False)
            column.set_attributes(rentext, markup=col_index(COL_PERMS, i))
            self.treeview[i].append_column(column)
            self.columns_dict[i]["permissions"] = column

        for i in range(3):
            selection = self.treeview[i].get_selection()
            selection.set_mode(Gtk.SelectionMode.MULTIPLE)
            selection.connect('changed', self.on_treeview_selection_changed, i)
            self.scrolledwindow[i].get_vadjustment().connect(
                "value-changed", self._sync_vscroll)
            self.scrolledwindow[i].get_hadjustment().connect(
                "value-changed", self._sync_hscroll)
            # Revert overlay scrolling that messes with widget interactivity
            if hasattr(self.scrolledwindow[i], 'set_overlay_scrolling'):
                self.scrolledwindow[i].set_overlay_scrolling(False)
        self.linediffs = [[], []]

        self.update_treeview_columns(settings, 'folder-columns')
        settings.connect('changed::folder-columns',
                         self.update_treeview_columns)

        self.update_comparator()
        self.connect("notify::shallow-comparison", self.update_comparator)
        self.connect("notify::time-resolution", self.update_comparator)
        self.connect("notify::ignore-blank-lines", self.update_comparator)
        self.connect("notify::apply-text-filters", self.update_comparator)

        self.state_filters = []
        for s in self.state_actions:
            if self.state_actions[s][0] in self.props.status_filters:
                self.state_filters.append(s)
                action_name = self.state_actions[s][1]
                self.actiongroup.get_action(action_name).set_active(True)

        self._scan_in_progress = 0

    def queue_draw(self):
        for treeview in self.treeview:
            treeview.queue_draw()
        for diffmap in self.diffmap:
            diffmap.queue_draw()

    def update_comparator(self, *args):
        comparison_args = {
            'shallow-comparison': self.props.shallow_comparison,
            'time-resolution': self.props.time_resolution,
            'apply-text-filters': self.props.apply_text_filters,
            'ignore_blank_lines': self.props.ignore_blank_lines,
        }
        self.file_compare = functools.partial(
            _files_same, comparison_args=comparison_args)
        self.refresh()

    def update_treeview_columns(self, settings, key):
        """Update the visibility and order of columns"""
        columns = settings.get_value(key)
        for i, treeview in enumerate(self.treeview):
            extra_cols = False
            last_column = treeview.get_column(0)
            for column_name, visible in columns:
                extra_cols = extra_cols or visible
                current_column = self.columns_dict[i][column_name]
                current_column.set_visible(visible)
                treeview.move_column_after(current_column, last_column)
                last_column = current_column
            treeview.set_headers_visible(extra_cols)

    def on_custom_filter_menu_toggled(self, item):
        if item.get_active():
            self.custom_popup.connect("deactivate",
                                      lambda popup: item.set_active(False))
            self.custom_popup.popup(None, None,
                                    misc.position_menu_under_widget,
                                    self.filter_menu_button, 1,
                                    Gtk.get_current_event_time())

    def _cleanup_filter_menu_button(self, ui):
        if self.popup_deactivate_id:
            self.popup_menu.disconnect(self.popup_deactivate_id)
        if self.custom_merge_id:
            ui.remove_ui(self.custom_merge_id)
        if self.filter_actiongroup in ui.get_action_groups():
            ui.remove_action_group(self.filter_actiongroup)

    def _create_filter_menu_button(self, ui):
        ui.insert_action_group(self.filter_actiongroup, -1)
        self.custom_merge_id = ui.new_merge_id()
        for x in self.filter_ui:
            ui.add_ui(self.custom_merge_id, *x)
        self.popup_deactivate_id = self.popup_menu.connect("deactivate", self.on_popup_deactivate_event)
        self.custom_popup = ui.get_widget("/CustomPopup")
        self.filter_menu_button = ui.get_widget("/Toolbar/FilterActions/CustomFilterMenu")
        label = misc.make_tool_button_widget(self.filter_menu_button.props.label)
        self.filter_menu_button.set_label_widget(label)

    def on_container_switch_in_event(self, ui):
        melddoc.MeldDoc.on_container_switch_in_event(self, ui)
        self._create_filter_menu_button(ui)
        self.ui_manager = ui

    def on_container_switch_out_event(self, ui):
        self._cleanup_filter_menu_button(ui)
        melddoc.MeldDoc.on_container_switch_out_event(self, ui)

    def on_file_filters_changed(self, app):
        self._cleanup_filter_menu_button(self.ui_manager)
        relevant_change = self.create_name_filters()
        self._create_filter_menu_button(self.ui_manager)
        if relevant_change:
            self.refresh()

    def create_name_filters(self):
        # Ordering of name filters is irrelevant
        old_active = set([f.filter_string for f in self.name_filters
                          if f.active])
        new_active = set([f.filter_string for f in meldsettings.file_filters
                          if f.active])
        active_filters_changed = old_active != new_active

        self.name_filters = [copy.copy(f) for f in meldsettings.file_filters]
        actions = []
        disabled_actions = []
        self.filter_ui = []
        for i, f in enumerate(self.name_filters):
            name = "Hide%d" % i
            callback = lambda b, i=i: self._update_name_filter(b, i)
            actions.append((name, None, f.label, None, _("Hide %s") % f.label, callback, f.active))
            self.filter_ui.append(["/CustomPopup" , name, name, Gtk.UIManagerItemType.MENUITEM, False])
            self.filter_ui.append(["/Menubar/ViewMenu/FileFilters" , name, name, Gtk.UIManagerItemType.MENUITEM, False])
            if f.filter is None:
                disabled_actions.append(name)

        self.filter_actiongroup = Gtk.ActionGroup(name="DirdiffFilterActions")
        self.filter_actiongroup.add_toggle_actions(actions)
        for name in disabled_actions:
            self.filter_actiongroup.get_action(name).set_sensitive(False)

        return active_filters_changed

    def on_text_filters_changed(self, app):
        relevant_change = self.create_text_filters()
        if relevant_change:
            self.refresh()

    def create_text_filters(self):
        # In contrast to file filters, ordering of text filters can matter
        old_active = [f.filter_string for f in self.text_filters if f.active]
        new_active = [f.filter_string for f in meldsettings.text_filters
                      if f.active]
        active_filters_changed = old_active != new_active

        self.text_filters = [copy.copy(f) for f in meldsettings.text_filters]

        return active_filters_changed

    def _do_to_others(self, master, objects, methodname, args):
        if self.do_to_others_lock:
            return

        self.do_to_others_lock = True
        try:
            others = [o for o in objects[:self.num_panes] if o != master]
            for o in others:
                method = getattr(o, methodname)
                method(*args)
        finally:
            self.do_to_others_lock = False

    def _sync_vscroll(self, adjustment):
        adjs = [sw.get_vadjustment() for sw in self.scrolledwindow]
        self._do_to_others(adjustment, adjs, "set_value",
                           (adjustment.get_value(), ))

    def _sync_hscroll(self, adjustment):
        adjs = [sw.get_hadjustment() for sw in self.scrolledwindow]
        self._do_to_others(adjustment, adjs, "set_value",
                           (adjustment.get_value(), ))

    def _get_focused_pane(self):
        for i, treeview in enumerate(self.treeview):
            if treeview.is_focus():
                return i
        return None

    def file_deleted(self, path, pane):
        # is file still extant in other pane?
        it = self.model.get_iter(path)
        files = self.model.value_paths(it)
        is_present = [ os.path.exists(f) for f in files ]
        if 1 in is_present:
            self._update_item_state(it)
        else: # nope its gone
            self.model.remove(it)
        self._update_diffmaps()

    def file_created(self, path, pane):
        it = self.model.get_iter(path)
        root = Gtk.TreePath.new_first()
        while it and self.model.get_path(it) != root:
            self._update_item_state( it )
            it = self.model.iter_parent(it)
        self._update_diffmaps()

    def on_fileentry_file_set(self, entry):
        files = [e.get_file() for e in self.fileentry[:self.num_panes]]
        paths = [f.get_path() for f in files]
        self.set_locations(paths)

    def set_locations(self, locations):
        self.set_num_panes(len(locations))
        # This is difficult to trigger, and to test. Most of the time here we
        # will actually have had UTF-8 from GTK, which has been unicode-ed by
        # the time we get this far. This is a fallback, and may be wrong!
        locations = list(locations)
        for i, l in enumerate(locations):
            if not isinstance(l, unicode):
                locations[i] = l.decode(sys.getfilesystemencoding())
        locations = [os.path.abspath(l) if l else '' for l in locations]
        self.current_path = None
        self.model.clear()
        for m in self.msgarea_mgr:
            m.clear()
        for pane, loc in enumerate(locations):
            if loc:
                self.fileentry[pane].set_filename(loc)
        child = self.model.add_entries(None, locations)
        self.treeview0.grab_focus()
        self._update_item_state(child)
        self.recompute_label()
        self.scheduler.remove_all_tasks()
        self.recursively_update(Gtk.TreePath.new_first())
        self._update_diffmaps()

    def get_comparison(self):
        root = self.model.get_iter_first()
        if root:
            folders = self.model.value_paths(root)
        else:
            folders = []
        return recent.TYPE_FOLDER, folders

    def recursively_update( self, path ):
        """Recursively update from tree path 'path'.
        """
        it = self.model.get_iter( path )
        child = self.model.iter_children( it )
        while child:
            self.model.remove(child)
            child = self.model.iter_children( it )
        self._update_item_state(it)
        self._scan_in_progress += 1
        self.scheduler.add_task(self._search_recursively_iter(path))

    def _search_recursively_iter(self, rootpath):
        for t in self.treeview:
            sel = t.get_selection()
            sel.unselect_all()

        yield _("[%s] Scanning %s") % (self.label_text, "")
        prefixlen = 1 + len( self.model.value_path( self.model.get_iter(rootpath), 0 ) )
        symlinks_followed = set()
        # TODO: This is horrible.
        if isinstance(rootpath, tuple):
            rootpath = Gtk.TreePath(rootpath)
        todo = [rootpath]
        expanded = set()

        tuple_tree_path = lambda p: tuple(p.get_indices())

        shadowed_entries = []
        invalid_filenames = []
        while len(todo):
            todo.sort() # depth first
            path = todo.pop(0)
            it = self.model.get_iter( path )
            roots = self.model.value_paths( it )

            # Buggy ordering when deleting rows means that we sometimes try to
            # recursively update files; this fix seems the least invasive.
            if not any(os.path.isdir(root) for root in roots):
                continue

            yield _("[%s] Scanning %s") % (self.label_text, roots[0][prefixlen:])
            differences = False
            encoding_errors = []

            canonicalize = None
            if self.actiongroup.get_action("IgnoreCase").get_active():
                canonicalize = lambda x : x.lower()
            dirs = CanonicalListing(self.num_panes, canonicalize)
            files = CanonicalListing(self.num_panes, canonicalize)

            for pane, root in enumerate(roots):
                if not os.path.isdir(root):
                    continue

                try:
                    entries = os.listdir(root)
                except OSError as err:
                    self.model.add_error(it, err.strerror, pane)
                    differences = True
                    continue

                for f in self.name_filters:
                    if not f.active or f.filter is None:
                        continue
                    entries = [e for e in entries if f.filter.match(e) is None]

                for e in entries:
                    try:
                        if not isinstance(e, unicode):
                            e = e.decode('utf8')
                    except UnicodeDecodeError:
                        approximate_name = e.decode('utf8', 'replace')
                        encoding_errors.append((pane, approximate_name))
                        continue

                    try:
                        s = os.lstat(os.path.join(root, e))
                    # Covers certain unreadable symlink cases; see bgo#585895
                    except OSError as err:
                        error_string = e + err.strerror
                        self.model.add_error(it, error_string, pane)
                        continue

                    if stat.S_ISLNK(s.st_mode):
                        if self.props.ignore_symlinks:
                            continue
                        key = (s.st_dev, s.st_ino)
                        if key in symlinks_followed:
                            continue
                        symlinks_followed.add(key)
                        try:
                            s = os.stat(os.path.join(root, e))
                            if stat.S_ISREG(s.st_mode):
                                files.add(pane, e)
                            elif stat.S_ISDIR(s.st_mode):
                                dirs.add(pane, e)
                        except OSError as err:
                            if err.errno == errno.ENOENT:
                                error_string = e + ": Dangling symlink"
                            else:
                                error_string = e + err.strerror
                            self.model.add_error(it, error_string, pane)
                            differences = True
                    elif stat.S_ISREG(s.st_mode):
                        files.add(pane, e)
                    elif stat.S_ISDIR(s.st_mode):
                        dirs.add(pane, e)
                    else:
                        # FIXME: Unhandled stat type
                        pass

            for pane, f in encoding_errors:
                invalid_filenames.append((pane, roots[pane], f))

            for pane, f1, f2 in dirs.errors + files.errors:
                shadowed_entries.append((pane, roots[pane], f1, f2))

            alldirs = self._filter_on_state(roots, dirs.get())
            allfiles = self._filter_on_state(roots, files.get())

            if alldirs or allfiles:
                for names in alldirs:
                    entries = [os.path.join(r, n) for r, n in zip(roots, names)]
                    child = self.model.add_entries(it, entries)
                    differences |= self._update_item_state(child)
                    todo.append(self.model.get_path(child))
                for names in allfiles:
                    entries = [os.path.join(r, n) for r, n in zip(roots, names)]
                    child = self.model.add_entries(it, entries)
                    differences |= self._update_item_state(child)
            else:
                # Our subtree is empty, or has been filtered to be empty
                if (tree.STATE_NORMAL in self.state_filters or
                        not all(os.path.isdir(f) for f in roots)):
                    self.model.add_empty(it)
                    if self.model.iter_parent(it) is None:
                        expanded.add(tuple_tree_path(rootpath))
                else:
                    # At this point, we have an empty folder tree node; we can
                    # prune this and any ancestors that then end up empty.
                    while not self.model.iter_has_child(it):
                        parent = self.model.iter_parent(it)

                        # In our tree, there is always a top-level parent with
                        # no siblings. If we're here, we have an empty tree.
                        if parent is None:
                            self.model.add_empty(it)
                            expanded.add(tuple_tree_path(rootpath))
                            break

                        # Remove the current row, and then revalidate all
                        # sibling paths on the stack by removing and
                        # readding them.
                        had_siblings = self.model.remove(it)
                        if had_siblings:
                            parent_path = self.model.get_path(parent)
                            for path in todo:
                                if parent_path.is_ancestor(path):
                                    path.prev()

                        it = parent

            if differences:
                expanded.add(tuple_tree_path(path))

        if invalid_filenames or shadowed_entries:
            self._show_tree_wide_errors(invalid_filenames, shadowed_entries)
        elif not expanded:
            self._show_identical_status()

        self.treeview[0].expand_to_path(Gtk.TreePath(("0",)))
        for path in sorted(expanded):
            self.treeview[0].expand_to_path(Gtk.TreePath(path))
        yield _("[%s] Done") % self.label_text

        self.scheduler.add_task(self.on_treeview_cursor_changed)
        self._scan_in_progress -= 1
        self.treeview[0].get_selection().select_path(Gtk.TreePath.new_first())
        self._update_diffmaps()

    def _show_identical_status(self):
        primary = _("Folders have no differences")
        identical_note = _(
            "Contents of scanned files in folders are identical.")
        shallow_note = _(
            "Scanned files in folders appear identical, but contents have not "
            "been scanned.")
        file_filter_qualifier = _(
            "File filters are in use, so not all files have been scanned.")
        text_filter_qualifier = _(
            "Text filters are in use and may be masking content differences.")

        is_shallow = self.props.shallow_comparison
        have_file_filters = any(f.active for f in self.name_filters)
        have_text_filters = any(f.active for f in self.text_filters)

        secondary = [shallow_note if is_shallow else identical_note]
        if have_file_filters:
            secondary.append(file_filter_qualifier)
        if not is_shallow and have_text_filters:
            secondary.append(text_filter_qualifier)
        secondary = " ".join(secondary)

        for pane in range(self.num_panes):
            msgarea = self.msgarea_mgr[pane].new_from_text_and_icon(
                'dialog-information-symbolic', primary, secondary)
            button = msgarea.add_button(_("Hide"), Gtk.ResponseType.CLOSE)
            if pane == 0:
                button.props.label = _("Hi_de")

            def clear_all(*args):
                for p in range(self.num_panes):
                    self.msgarea_mgr[p].clear()
            msgarea.connect("response", clear_all)
            msgarea.show_all()


    def _show_tree_wide_errors(self, invalid_filenames, shadowed_entries):
        header = _("Multiple errors occurred while scanning this folder")
        invalid_header = _("Files with invalid encodings found")
        # TRANSLATORS: This is followed by a list of files
        invalid_secondary = _("Some files were in an incorrect encoding. "
                              "The names are something like:")
        shadowed_header = _("Files hidden by case insensitive comparison")
        # TRANSLATORS: This is followed by a list of files
        shadowed_secondary = _("You are running a case insensitive comparison "
                               "on a case sensitive filesystem. The following "
                               "files in this folder are hidden:")

        invalid_entries = [[] for i in range(self.num_panes)]
        for pane, root, f in invalid_filenames:
            invalid_entries[pane].append(os.path.join(root, f))

        formatted_entries = [[] for i in range(self.num_panes)]
        for pane, root, f1, f2 in shadowed_entries:
            paths = [os.path.join(root, f) for f in (f1, f2)]
            entry_str = _("'%s' hidden by '%s'") % (paths[0], paths[1])
            formatted_entries[pane].append(entry_str)

        if invalid_filenames or shadowed_entries:
            for pane in range(self.num_panes):
                invalid = "\n".join(invalid_entries[pane])
                shadowed = "\n".join(formatted_entries[pane])
                if invalid and shadowed:
                    messages = (invalid_secondary, invalid, "",
                                shadowed_secondary, shadowed)
                elif invalid:
                    header = invalid_header
                    messages = (invalid_secondary, invalid)
                elif shadowed:
                    header = shadowed_header
                    messages = (shadowed_secondary, shadowed)
                else:
                    continue
                secondary = "\n".join(messages)
                self.msgarea_mgr[pane].add_dismissable_msg(
                    'dialog-error-symbolic', header, secondary)

    def copy_selected(self, direction):
        assert direction in (-1, 1)
        src_pane = self._get_focused_pane()
        if src_pane is None:
            return

        dst_pane = src_pane + direction
        assert dst_pane >= 0 and dst_pane < self.num_panes
        paths = self._get_selected_paths(src_pane)
        paths.reverse()
        model = self.model
        for path in paths:  # filter(lambda x: x.name is not None, sel):
            it = model.get_iter(path)
            name = model.value_path(it, src_pane)
            if name is None:
                continue
            src = model.value_path(it, src_pane)
            dst = model.value_path(it, dst_pane)
            try:
                if os.path.isfile(src):
                    dstdir = os.path.dirname(dst)
                    if not os.path.exists(dstdir):
                        os.makedirs(dstdir)
                    misc.copy2(src, dstdir)
                    self.file_created(path, dst_pane)
                elif os.path.isdir(src):
                    if os.path.exists(dst):
                        parent_name = os.path.dirname(dst)
                        folder_name = os.path.basename(dst)
                        dialog_buttons = [
                            (_("_Cancel"), Gtk.ResponseType.CANCEL),
                            (_("_Replace"), Gtk.ResponseType.OK),
                        ]
                        replace = misc.modal_dialog(
                            primary=_(u"Replace folder “%s”?") % folder_name,
                            secondary=_(
                                u"Another folder with the same name already "
                                u"exists in “%s”.\n"
                                u"If you replace the existing folder, all "
                                u"files in it will be lost.") % parent_name,
                            buttons=dialog_buttons,
                            messagetype=Gtk.MessageType.WARNING,
                        )
                        if replace != Gtk.ResponseType.OK:
                            continue
                    misc.copytree(src, dst)
                    self.recursively_update(path)
            except (OSError, IOError, shutil.Error) as err:
                misc.error_dialog(
                    _("Error copying file"),
                    _("Couldn't copy %s\nto %s.\n\n%s") % (
                        GLib.markup_escape_text(src),
                        GLib.markup_escape_text(dst),
                        GLib.markup_escape_text(str(err)),
                    )
                )

    def delete_selected(self):
        """Delete all selected files/folders recursively.
        """
        # reverse so paths dont get changed
        pane = self._get_focused_pane()
        if pane is not None:
            paths = self._get_selected_paths(pane)
            paths.reverse()
            for path in paths:
                it = self.model.get_iter(path)
                name = self.model.value_path(it, pane)
                try:
                    gfile = Gio.File.new_for_path(name)
                    gfile.trash(None)
                    self.file_deleted(path, pane)
                except GLib.GError as e:
                    misc.error_dialog(_("Error deleting %s") % name, str(e))

    def on_treemodel_row_deleted(self, model, path):

        # TODO: Move this and path tools to new tree helper module
        def refocus_deleted_path(model, path):
            # Since the passed path has been deleted, either the path is now a
            # valid successor, or there are no successors. If valid, return it.
            # If not, and the path has a predecessor sibling (immediate or
            # otherwise), then return that. If there are no siblings, traverse
            # parents until we get a valid path, and return that.

            def tree_path_prev(path):
                if not path or path[-1] == 0:
                    return None
                return path[:-1] + (path[-1] - 1,)

            def tree_path_up(path):
                if not path:
                    return None
                return path[:-1]

            def valid_path(model, path):
                try:
                    model.get_iter(path)
                    return True
                except ValueError:
                    return False

            if valid_path(model, path):
                return path

            new_path = tree_path_prev(path)
            while new_path:
                if valid_path(model, new_path):
                    return new_path
                new_path = tree_path_prev(new_path)

            new_path = tree_path_up(path)
            while new_path:
                if valid_path(model, new_path):
                    return new_path
                new_path = tree_path_up(new_path)

            return None

        if self.current_path == path:
            self.current_path = refocus_deleted_path(model, path)
            if self.current_path and self.focus_pane:
                self.focus_pane.set_cursor(self.current_path)

        self.row_expansions = set()

    def on_treeview_selection_changed(self, selection, pane):
        if not self.treeview[pane].is_focus():
            return
        have_selection = bool(selection.count_selected_rows())
        get_action = self.actiongroup.get_action

        if have_selection:
            is_valid = True
            for path in selection.get_selected_rows()[1]:
                state = self.model.get_state(self.model.get_iter(path), pane)
                if state in (tree.STATE_ERROR, tree.STATE_NONEXIST):
                    is_valid = False
                    break

            busy = self._scan_in_progress > 0

            get_action("DirCompare").set_sensitive(True)
            get_action("Hide").set_sensitive(True)
            get_action("DirDelete").set_sensitive(
                is_valid and not busy)
            get_action("DirCopyLeft").set_sensitive(
                is_valid and not busy and pane > 0)
            get_action("DirCopyRight").set_sensitive(
                is_valid and not busy and pane + 1 < self.num_panes)
            if self.main_actiongroup:
                act = self.main_actiongroup.get_action("OpenExternal")
                act.set_sensitive(is_valid)
        else:
            for action in ("DirCompare", "DirCopyLeft", "DirCopyRight",
                           "DirDelete", "Hide"):
                get_action(action).set_sensitive(False)
            if self.main_actiongroup:
                act = self.main_actiongroup.get_action("OpenExternal")
                act.set_sensitive(False)

    def on_treeview_cursor_changed(self, *args):
        pane = self._get_focused_pane()
        if pane is None or len(self.model) == 0:
            return

        cursor_path, cursor_col = self.treeview[pane].get_cursor()
        if not cursor_path:
            self.emit("next-diff-changed", False, False)
            self.current_path = cursor_path
            return

        # If invoked directly rather than through a callback, we always check
        if not args:
            skip = False
        else:
            try:
                old_cursor = self.model.get_iter(self.current_path)
            except (ValueError, TypeError):
                # An invalid path gives ValueError; None gives a TypeError
                skip = False
            else:
                # We can skip recalculation if the new cursor is between
                # the previous/next bounds, and we weren't on a changed row
                state = self.model.get_state(old_cursor, 0)
                if state not in (tree.STATE_NORMAL, tree.STATE_EMPTY):
                    skip = False
                else:
                    if self.prev_path is None and self.next_path is None:
                        skip = True
                    elif self.prev_path is None:
                        skip = cursor_path < self.next_path
                    elif self.next_path is None:
                        skip = self.prev_path < cursor_path
                    else:
                        skip = self.prev_path < cursor_path < self.next_path

        if not skip:
            prev, next = self.model._find_next_prev_diff(cursor_path)
            self.prev_path, self.next_path = prev, next
            have_next_diffs = (prev is not None, next is not None)
            self.emit("next-diff-changed", *have_next_diffs)
        self.current_path = cursor_path

    def on_treeview_key_press_event(self, view, event):
        pane = self.treeview.index(view)
        tree = None
        if Gdk.KEY_Right == event.keyval:
            if pane+1 < self.num_panes:
                tree = self.treeview[pane+1]
        elif Gdk.KEY_Left == event.keyval:
            if pane-1 >= 0:
                tree = self.treeview[pane-1]
        if tree is not None:
            paths = self._get_selected_paths(pane)
            view.get_selection().unselect_all()
            tree.grab_focus()
            tree.get_selection().unselect_all()
            if len(paths):
                tree.set_cursor(paths[0])
                for p in paths:
                    tree.get_selection().select_path(p)
            tree.emit("cursor-changed")
        return event.keyval in (Gdk.KEY_Left, Gdk.KEY_Right) #handled

    def on_treeview_row_activated(self, view, path, column):
        pane = self.treeview.index(view)
        rows = self.model.value_paths(self.model.get_iter(path))
        # Click a file: compare; click a directory: expand; click a missing
        # entry: check the next neighbouring entry
        pane_ordering = ((0, 1, 2), (1, 2, 0), (2, 1, 0))
        for p in pane_ordering[pane]:
            if p < self.num_panes and rows[p] and os.path.exists(rows[p]):
                pane = p
                break
        if not rows[pane]:
            return
        if os.path.isfile(rows[pane]):
            self.emit("create-diff", [r for r in rows if os.path.isfile(r)],
                      {})
        elif os.path.isdir(rows[pane]):
            if view.row_expanded(path):
                view.collapse_row(path)
            else:
                view.expand_row(path, False)

    def on_treeview_row_expanded(self, view, it, path):
        self.row_expansions.add(str(path))
        for row in self.model[path].iterchildren():
            if str(row.path) in self.row_expansions:
                view.expand_row(row.path, False)

        self._do_to_others(view, self.treeview, "expand_row", (path, False))
        self._update_diffmaps()

    def on_treeview_row_collapsed(self, view, me, path):
        self.row_expansions.discard(str(path))
        self._do_to_others(view, self.treeview, "collapse_row", (path,))
        self._update_diffmaps()

    def on_popup_deactivate_event(self, popup):
        for (treeview, inid, outid) in zip(self.treeview, self.focus_in_events, self.focus_out_events):
            treeview.handler_unblock(inid)
            treeview.handler_unblock(outid)

    def on_treeview_focus_in_event(self, tree, event):
        self.focus_pane = tree
        pane = self.treeview.index(tree)
        self.on_treeview_selection_changed(tree.get_selection(), pane)
        tree.emit("cursor-changed")

    def on_treeview_focus_out_event(self, tree, event):
        for action in ("DirCompare", "DirCopyLeft", "DirCopyRight",
                       "DirDelete", "Hide"):
            self.actiongroup.get_action(action).set_sensitive(False)
        try:
            self.main_actiongroup.get_action("OpenExternal").set_sensitive(
                False)
        except AttributeError:
            pass

    def on_button_diff_clicked(self, button):
        pane = self._get_focused_pane()
        if pane is None:
            return

        selected = self._get_selected_paths(pane)
        for row in selected:
            row_paths = self.model.value_paths(self.model.get_iter(row))
            paths = [p for p in row_paths if os.path.exists(p)]
            self.emit("create-diff", paths, {})

    def on_button_copy_left_clicked(self, button):
        self.copy_selected(-1)
    def on_button_copy_right_clicked(self, button):
        self.copy_selected(1)
    def on_button_delete_clicked(self, button):
        self.delete_selected()

    def open_external(self):
        pane = self._get_focused_pane()
        if pane is None:
            return
        path = lambda p: self.model.value_path(self.model.get_iter(p), pane)
        files = [path(p) for p in self._get_selected_paths(pane)]
        files = [f for f in files if f]
        if files:
            self._open_files(files)

    def on_button_ignore_case_toggled(self, button):
        self.refresh()

    def on_filter_state_toggled(self, button):
        active_action = lambda a: self.actiongroup.get_action(a).get_active()
        active_filters = [a for a in self.state_actions if \
                          active_action(self.state_actions[a][1])]

        if set(active_filters) == set(self.state_filters):
            return

        state_strs = [self.state_actions[s][0] for s in active_filters]
        self.state_filters = active_filters
        # TODO: Updating the property won't have any effect on its own
        self.props.status_filters = state_strs
        self.refresh()

    def _update_name_filter(self, button, idx):
        self.name_filters[idx].active = button.get_active()
        self.refresh()

    def on_filter_hide_current_clicked(self, button):
        pane = self._get_focused_pane()
        if pane is not None:
            paths = self._get_selected_paths(pane)
            paths.reverse()
            for p in paths:
                self.model.remove( self.model.get_iter(p) )

        #
        # Selection
        #
    def _get_selected_paths(self, pane):
        assert pane is not None
        return self.treeview[pane].get_selection().get_selected_rows()[1]

        #
        # Filtering
        #

    def _filter_on_state(self, roots, fileslist):
        """Get state of 'files' for filtering purposes.
           Returns STATE_NORMAL, STATE_NEW or STATE_MODIFIED

               roots - array of root directories
               fileslist - array of filename tuples of length len(roots)
        """
        assert len(roots) == self.model.ntree
        ret = []
        regexes = [f.filter for f in self.text_filters if f.active]
        for files in fileslist:
            curfiles = [ os.path.join( r, f ) for r,f in zip(roots,files) ]
            is_present = [ os.path.exists( f ) for f in curfiles ]
            all_present = 0 not in is_present
            if all_present:
                if self.file_compare(curfiles, regexes) in (
                        Same, SameFiltered, DodgySame):
                    state = tree.STATE_NORMAL
                else:
                    state = tree.STATE_MODIFIED
            else:
                state = tree.STATE_NEW
            # Always retain NORMAL folders for comparison; we remove these
            # later if they have no children.
            if (state in self.state_filters or
                    all(os.path.isdir(f) for f in curfiles)):
                ret.append( files )
        return ret

    def _update_item_state(self, it):
        """Update the state of the item at 'it'
        """
        files = self.model.value_paths(it)
        regexes = [f.filter for f in self.text_filters if f.active]

        def stat(f):
            try:
                return os.stat(f)
            except OSError:
                return None
        stats = [stat(f) for f in files[:self.num_panes]]
        sizes = [s.st_size if s else 0 for s in stats]
        perms = [s.st_mode if s else 0 for s in stats]

        # find the newest file, checking also that they differ
        mod_times = [s.st_mtime if s else 0 for s in stats]
        newest_index = mod_times.index( max(mod_times) )
        if mod_times.count( max(mod_times) ) == len(mod_times):
            newest_index = -1 # all same
        all_present = 0 not in mod_times
        if all_present:
            all_same = self.file_compare(files, regexes)
            all_present_same = all_same
        else:
            lof = []
            for j in range(len(mod_times)):
                if mod_times[j]:
                    lof.append( files[j] )
            all_same = Different
            all_present_same = self.file_compare(lof, regexes)
        different = 1
        one_isdir = [None for i in range(self.model.ntree)]
        locale_encoding = locale.getpreferredencoding()
        for j in range(self.model.ntree):
            if mod_times[j]:
                isdir = os.path.isdir( files[j] )
                # TODO: Differentiate the DodgySame case
                if all_same == Same or all_same == DodgySame:
                    self.model.set_path_state(it, j, tree.STATE_NORMAL, isdir)
                    different = 0
                elif all_same == SameFiltered:
                    self.model.set_path_state(it, j, tree.STATE_NOCHANGE, isdir)
                    different = 0
                # TODO: Differentiate the SameFiltered and DodgySame cases
                elif all_present_same in (Same, SameFiltered, DodgySame):
                    self.model.set_path_state(it, j, tree.STATE_NEW, isdir)
                elif all_same == FileError or all_present_same == FileError:
                    self.model.set_path_state(it, j, tree.STATE_ERROR, isdir)
                # Different and DodgyDifferent
                else:
                    self.model.set_path_state(it, j, tree.STATE_MODIFIED, isdir)
                self.model.set_value(it,
                    self.model.column_index(COL_EMBLEM, j),
                    j == newest_index and "emblem-meld-newer-file" or None)
                one_isdir[j] = isdir

                # A DateCellRenderer would be nicer, but potentially very slow
                TIME = self.model.column_index(COL_TIME, j)
                mod_datetime = datetime.datetime.fromtimestamp(mod_times[j])
                time_str = mod_datetime.strftime("%a %d %b %Y %H:%M:%S")
                time_str = time_str.decode(locale_encoding, errors='replace')
                self.model.set_value(it, TIME, time_str)

                def natural_size(bytes):
                    suffixes = (
                            'B', 'kB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'
                            )
                    size = float(bytes)
                    unit = 0
                    while size > 1000 and unit < len(suffixes) - 1:
                        size /= 1000
                        unit += 1
                    format_str = "%.1f %s" if unit > 0 else "%d %s"
                    return format_str % (size, suffixes[unit])

                # A SizeCellRenderer would be nicer, but potentially very slow
                SIZE = self.model.column_index(COL_SIZE, j)
                size_str = natural_size(sizes[j])
                self.model.set_value(it, SIZE, size_str)

                def format_mode(mode):
                    perms = []
                    rwx = ((4, 'r'), (2, 'w'), (1, 'x'))
                    for group_index in (6, 3, 0):
                        group = mode >> group_index & 7
                        perms.extend([p if group & i else '-' for i, p in rwx])
                    return "".join(perms)

                PERMS = self.model.column_index(COL_PERMS, j)
                perm_str = format_mode(perms[j])
                self.model.set_value(it, PERMS, perm_str)

        for j in range(self.model.ntree):
            if not mod_times[j]:
                self.model.set_path_state(it, j, tree.STATE_NONEXIST,
                                          True in one_isdir)
        return different

    def popup_in_pane(self, pane, event):
        for (treeview, inid, outid) in zip(self.treeview, self.focus_in_events, self.focus_out_events):
            treeview.handler_block(inid)
            treeview.handler_block(outid)
        self.actiongroup.get_action("DirCopyLeft").set_sensitive(pane > 0)
        self.actiongroup.get_action("DirCopyRight").set_sensitive(pane+1 < self.num_panes)
        if event:
            button = event.button
            time = event.time
        else:
            button = 0
            time = Gtk.get_current_event_time()
        self.popup_menu.popup(None, None, None, None, button, time)

    def on_treeview_popup_menu(self, treeview):
        self.popup_in_pane(self.treeview.index(treeview), None)
        return True

    def on_treeview_button_press_event(self, treeview, event):
        # Unselect any selected files in other panes
        for t in [v for v in self.treeview[:self.num_panes] if v != treeview]:
            t.get_selection().unselect_all()

        if event.button == 3:
            treeview.grab_focus()
            path = treeview.get_path_at_pos(int(event.x), int(event.y))
            if path is None:
                return False
            selection = treeview.get_selection()
            model, rows = selection.get_selected_rows()

            if path[0] not in rows:
                selection.unselect_all()
                selection.select_path(path[0])
                treeview.set_cursor(path[0])

            self.popup_in_pane(self.treeview.index(treeview), event)
            return True
        return False

    def get_state_traversal(self, diffmapindex):
        def tree_state_iter():
            treeindex = (0, self.num_panes-1)[diffmapindex]
            treeview = self.treeview[treeindex]
            row_states = []
            def recurse_tree_states(rowiter):
                row_states.append(self.model.get_state(rowiter.iter, treeindex))
                if treeview.row_expanded(rowiter.path):
                    for row in rowiter.iterchildren():
                        recurse_tree_states(row)
            recurse_tree_states(next(iter(self.model)))
            row_states.append(None)

            numlines = float(len(row_states) - 1)
            chunkstart, laststate = 0, row_states[0]
            for index, state in enumerate(row_states):
                if state != laststate:
                    action = self.chunk_type_map[laststate]
                    if action is not None:
                        yield (action, chunkstart / numlines, index / numlines)
                    chunkstart, laststate = index, state
        return tree_state_iter

    def set_num_panes(self, n):
        if n != self.num_panes and n in (1,2,3):
            self.model = DirDiffTreeStore(n)
            for i in range(n):
                self.treeview[i].set_model(self.model)
            self.model.connect("row-deleted", self.on_treemodel_row_deleted)

            for (w, i) in zip(self.diffmap, (0, n - 1)):
                scroll = self.scrolledwindow[i].get_vscrollbar()
                idx = 1 if i else 0
                w.setup(scroll, self.get_state_traversal(idx))

            for w in self.linkmap:
                w.associate(self)

            for widget in (
                    self.vbox[:n] + self.file_toolbar[:n] + self.diffmap[:n] +
                    self.linkmap[:n - 1] + self.dummy_toolbar_linkmap[:n - 1]):
                widget.show()

            for widget in (
                    self.vbox[n:] + self.file_toolbar[n:] + self.diffmap[n:] +
                    self.linkmap[n - 1:] + self.dummy_toolbar_linkmap[n - 1:]):
                widget.hide()

            if self.num_panes != 0: # not first time through
                self.num_panes = n
                self.on_fileentry_file_set(None)
            else:
                self.num_panes = n

    def refresh(self):
        root = self.model.get_iter_first()
        if root:
            roots = self.model.value_paths(root)
            self.set_locations( roots )

    def recompute_label(self):
        root = self.model.get_iter_first()
        filenames = self.model.value_paths(root)
        filenames = [f or _('No folder') for f in filenames]
        if self.custom_labels:
            label_options = zip(self.custom_labels, filenames)
            shortnames = [l[0] or l[1] for l in label_options]
        else:
            shortnames = misc.shorten_names(*filenames)
        self.label_text = " : ".join(shortnames)
        self.tooltip_text = self.label_text
        self.label_changed()

    def set_labels(self, labels):
        labels = labels[:self.num_panes]
        extra = self.num_panes - len(labels)
        if extra:
            labels.extend([""] * extra)
        self.custom_labels = labels
        self.recompute_label()

    def _update_diffmaps(self):
        for diffmap in self.diffmap:
            diffmap.on_diffs_changed()
            diffmap.queue_draw()

    def on_file_changed(self, changed_filename):
        """When a file has changed, try to find it in our tree
           and update its status if necessary
        """
        model = self.model
        changed_paths = []
        # search each panes tree for changed_filename
        for pane in range(self.num_panes):
            it = model.get_iter_first()
            current = model.value_path(it, pane).split(os.sep)
            changed = changed_filename.split(os.sep)
            # early exit. does filename begin with root?
            try:
                if changed[:len(current)] != current:
                    continue
            except IndexError:
                continue
            changed = changed[len(current):]
            # search the tree component at a time
            for component in changed:
                child = model.iter_children( it )
                while child:
                    child_path = model.value_path(child, pane)
                    # Found the changed path
                    if child_path and component == os.path.basename(child_path):
                        it = child
                        break
                    child = self.model.iter_next(child)
                if not it:
                    break
            # save if found and unique
            if it:
                path = model.get_path(it)
                if path not in changed_paths:
                    changed_paths.append(path)
        # do the update
        for path in changed_paths:
            self._update_item_state( model.get_iter(path) )
        self._update_diffmaps()

    def next_diff(self, direction):
        if self.focus_pane:
            pane = self.treeview.index(self.focus_pane)
        else:
            pane = 0
        if direction == Gdk.ScrollDirection.UP:
            path = self.prev_path
        else:
            path = self.next_path
        if path:
            self.treeview[pane].expand_to_path(path)
            self.treeview[pane].set_cursor(path)

    def on_refresh_activate(self, *extra):
        self.on_fileentry_file_set(None)

    def on_delete_event(self):
        for h in self.settings_handlers:
            meldsettings.disconnect(h)
        self.emit('close', 0)
        return Gtk.ResponseType.OK

    def on_find_activate(self, *extra):
        self.focus_pane.emit("start-interactive-search")
