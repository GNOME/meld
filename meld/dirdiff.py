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
import errno
import functools
import os
import shutil
import stat
import sys
from collections import namedtuple
from decimal import Decimal
from mmap import ACCESS_COPY, mmap

from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk

# TODO: Don't from-import whole modules
from meld import misc
from meld import tree
from meld.conf import _
from meld.iohelpers import trash_or_confirm
from meld.melddoc import MeldDoc
from meld.misc import all_same, apply_text_filters, with_focused_pane
from meld.recent import RecentType
from meld.settings import bind_settings, meldsettings, settings
from meld.treehelpers import refocus_deleted_path, tree_path_as_tuple
from meld.ui.cellrenderers import (
    CellRendererByteSize, CellRendererDate, CellRendererFileMode)
from meld.ui.emblemcellrenderer import EmblemCellRenderer
from meld.ui.gnomeglade import Component, ui_file


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
    """
    Remove blank lines from text.
    And normalize line ending
    """
    return b'\n'.join(filter(bool, text.splitlines()))


def _files_contents(files, stats):
    mmaps = []
    is_bin = False
    contents = [b'' for file_obj in files]

    for index, file_and_stat in enumerate(zip(files, stats)):
        file_obj, stat_ = file_and_stat
        # use mmap for files with size > CHUNK_SIZE
        data = b''
        if stat_.size > CHUNK_SIZE:
            data = mmap(file_obj.fileno(), 0, access=ACCESS_COPY)
            mmaps.append(data)
        else:
            data = file_obj.read()
        contents[index] = data

        # Rough test to see whether files are binary.
        chunk_size = min([stat_.size, CHUNK_SIZE])
        if b"\0" in data[:chunk_size]:
            is_bin = True

    return contents, mmaps, is_bin


def _contents_same(contents, file_size):
    other_files_index = list(range(1, len(contents)))
    chunk_range = zip(
        range(0, file_size, CHUNK_SIZE),
        range(CHUNK_SIZE, file_size + CHUNK_SIZE, CHUNK_SIZE)
    )

    for start, end in chunk_range:
        chunk = contents[0][start:end]
        for index in other_files_index:
            if not chunk == contents[index][start:end]:
                return Different


def _normalize(contents, ignore_blank_lines, regexes=()):
    contents = (bytes(c) for c in contents)
    # For probable text files, discard newline differences to match
    if ignore_blank_lines:
        contents = (remove_blank_lines(c) for c in contents)
    else:
        contents = (b"\n".join(c.splitlines()) for c in contents)

    if regexes:
        contents = (apply_text_filters(c, regexes) for c in contents)
        if ignore_blank_lines:
            # We re-remove blank lines here in case applying text
            # filters has caused more lines to be blank.
            contents = (remove_blank_lines(c) for c in contents)

    return contents


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
    stats = tuple([StatItem._make(os.stat(f)) for f in files])

    shallow_comparison = comparison_args['shallow-comparison']
    time_resolution_ns = comparison_args['time-resolution']
    ignore_blank_lines = comparison_args['ignore_blank_lines']
    apply_text_filters = comparison_args['apply-text-filters']

    need_contents = ignore_blank_lines or apply_text_filters

    regexes = tuple(regexes) if apply_text_filters else ()

    # If all entries are directories, they are considered to be the same
    if all([stat.S_ISDIR(s.mode) for s in stats]):
        return Same

    # If any entries are not regular files, consider them different
    if not all([stat.S_ISREG(s.mode) for s in stats]):
        return Different

    # Compare files superficially if the options tells us to
    if shallow_comparison:
        all_same_timestamp = all(
            s.shallow_equal(stats[0], time_resolution_ns) for s in stats[1:]
        )
        return DodgySame if all_same_timestamp else Different

    same_size = all_same([s.size for s in stats])
    # If there are no text filters, unequal sizes imply a difference
    if not need_contents and not same_size:
        return Different

    # Check the cache before doing the expensive comparison
    cache_key = (files, need_contents, regexes, ignore_blank_lines)
    cache = _cache.get(cache_key)
    if cache and cache.stats == stats:
        return cache.result

    # Open files and compare bit-by-bit
    result = None

    try:
        mmaps = []
        handles = [open(file_path, "rb") for file_path in files]
        try:
            contents, mmaps, is_bin = _files_contents(handles, stats)

            # compare files chunk-by-chunk
            if same_size:
                result = _contents_same(contents, stats[0].size)
            else:
                result = Different

            # normalize and compare files again
            if result == Different and need_contents and not is_bin:
                contents = _normalize(contents, ignore_blank_lines, regexes)
                result = SameFiltered if all_same(contents) else Different

        # Files are too large; we can't apply filters
        except (MemoryError, OverflowError):
            result = DodgySame if all_same(stats) else DodgyDifferent
        finally:
            for m in mmaps:
                m.close()
            for h in handles:
                h.close()
    except IOError:
        # Don't cache generic errors as results
        return FileError

    if result is None:
        result = Same

    _cache[cache_key] = CacheResult(stats, result)
    return result


EMBLEM_NEW = "emblem-meld-newer-file"
EMBLEM_SYMLINK = "emblem-symbolic-link"

COL_EMBLEM, COL_EMBLEM_SECONDARY, COL_SIZE, COL_TIME, COL_PERMS, COL_END = \
        range(tree.COL_END, tree.COL_END + 6)


class DirDiffTreeStore(tree.DiffTreeStore):
    def __init__(self, ntree):
        # FIXME: size should be a GObject.TYPE_UINT64, but we use -1 as a flag
        super().__init__(ntree, [str, str, GObject.TYPE_INT64, float, int])

    def add_error(self, parent, msg, pane):
        defaults = {
            COL_TIME: -1.0,
            COL_SIZE: -1,
            COL_PERMS: -1
        }
        super().add_error(parent, msg, pane, defaults)


class CanonicalListing:
    """Multi-pane lists with canonicalised matching and error detection"""

    def __init__(self, n, canonicalize=None):
        self.items = collections.defaultdict(lambda: [None] * n)
        self.errors = []
        self.canonicalize = canonicalize
        self.add = self.add_simple if canonicalize is None else self.add_canon

    def add_simple(self, pane, item):
        self.items[item][pane] = item

    def add_canon(self, pane, item):
        ci = self.canonicalize(item)
        if self.items[ci][pane] is None:
            self.items[ci][pane] = item
        else:
            self.errors.append((pane, item, self.items[ci][pane]))

    def get(self):
        def filled(seq):
            fill_value = next(s for s in seq if s)
            return tuple(s or fill_value for s in seq)

        return sorted(filled(v) for v in self.items.values())

    @staticmethod
    def canonicalize_lower(element):
        return element.lower()


class DirDiff(MeldDoc, Component):
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

    apply_text_filters = GObject.Property(
        type=bool,
        nick="Apply text filters",
        blurb=(
            "Whether text filters and other text sanitisation preferences "
            "should be applied when comparing file contents"),
        default=False,
    )
    ignore_blank_lines = GObject.Property(
        type=bool,
        nick="Ignore blank lines",
        blurb="Whether to ignore blank lines when comparing file contents",
        default=False,
    )
    ignore_symlinks = GObject.Property(
        type=bool,
        nick="Ignore symbolic links",
        blurb="Whether to follow symbolic links when comparing folders",
        default=False,
    )
    shallow_comparison = GObject.Property(
        type=bool,
        nick="Use shallow comparison",
        blurb="Whether to compare files based solely on size and mtime",
        default=False,
    )
    status_filters = GObject.Property(
        type=GObject.TYPE_STRV,
        nick="File status filters",
        blurb="Files with these statuses will be shown by the comparison.",
    )
    time_resolution = GObject.Property(
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
        tree.STATE_NOCHANGE: ("normal", "ShowSame"),
        tree.STATE_NEW: ("new", "ShowNew"),
        tree.STATE_MODIFIED: ("modified", "ShowModified"),
    }

    def __init__(self, num_panes):
        MeldDoc.__init__(self)
        Component.__init__(self, "dirdiff.ui", "dirdiff", ["DirdiffActions"])
        bind_settings(self)

        self.ui_file = ui_file("dirdiff-ui.xml")
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
        for treeview in self.treeview:
            treeview.set_search_equal_func(tree.treeview_search_cb, None)
        self.force_cursor_recalculate = False
        self.current_path, self.prev_path, self.next_path = None, None, None
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
            renicon = EmblemCellRenderer()
            column.pack_start(renicon, False)
            column.pack_start(rentext, True)
            column.set_attributes(rentext, markup=col_index(tree.COL_TEXT, i),
                                  foreground_rgba=col_index(tree.COL_FG, i),
                                  style=col_index(tree.COL_STYLE, i),
                                  weight=col_index(tree.COL_WEIGHT, i),
                                  strikethrough=col_index(tree.COL_STRIKE, i))
            column.set_attributes(
                renicon,
                icon_name=col_index(tree.COL_ICON, i),
                emblem_name=col_index(COL_EMBLEM, i),
                secondary_emblem_name=col_index(COL_EMBLEM_SECONDARY, i),
                icon_tint=col_index(tree.COL_TINT, i)
            )
            self.treeview[i].append_column(column)
            self.columns_dict[i]["name"] = column
            # Create file size CellRenderer
            column = Gtk.TreeViewColumn(_("Size"))
            column.set_resizable(True)
            rentext = CellRendererByteSize()
            column.pack_start(rentext, True)
            column.set_attributes(rentext, bytesize=col_index(COL_SIZE, i))
            self.treeview[i].append_column(column)
            self.columns_dict[i]["size"] = column
            # Create date-time CellRenderer
            column = Gtk.TreeViewColumn(_("Modification time"))
            column.set_resizable(True)
            rentext = CellRendererDate()
            column.pack_start(rentext, True)
            column.set_attributes(rentext, timestamp=col_index(COL_TIME, i))
            self.treeview[i].append_column(column)
            self.columns_dict[i]["modification time"] = column
            # Create permissions CellRenderer
            column = Gtk.TreeViewColumn(_("Permissions"))
            column.set_resizable(True)
            rentext = CellRendererFileMode()
            column.pack_start(rentext, False)
            column.set_attributes(rentext, file_mode=col_index(COL_PERMS, i))
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
        self.linediffs = [[], []]

        self.update_treeview_columns(settings, 'folder-columns')
        settings.connect('changed::folder-columns',
                         self.update_treeview_columns)

        self.update_comparator()
        self.connect("notify::shallow-comparison", self.update_comparator)
        self.connect("notify::time-resolution", self.update_comparator)
        self.connect("notify::ignore-blank-lines", self.update_comparator)
        self.connect("notify::apply-text-filters", self.update_comparator)

        # The list copying and state_filters reset here is because the action
        # toggled callback modifies the state while we're constructing it.
        self.state_filters = []
        state_filters = []
        status_filters = list(self.props.status_filters)
        for state, (filter_name, action_name) in self.state_actions.items():
            if filter_name in status_filters:
                state_filters.append(state)
                self.actiongroup.get_action(action_name).set_active(True)
        self.state_filters = state_filters

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
        if self.custom_merge_id:
            ui.remove_ui(self.custom_merge_id)
        if self.filter_actiongroup in ui.get_action_groups():
            ui.remove_action_group(self.filter_actiongroup)

    def _create_filter_menu_button(self, ui):
        ui.insert_action_group(self.filter_actiongroup, -1)
        self.custom_merge_id = ui.new_merge_id()
        for x in self.filter_ui:
            ui.add_ui(self.custom_merge_id, *x)
        self.custom_popup = ui.get_widget("/CustomPopup")
        self.filter_menu_button = ui.get_widget(
            "/Toolbar/FilterActions/CustomFilterMenu")
        label = misc.make_tool_button_widget(
            self.filter_menu_button.props.label)
        self.filter_menu_button.set_label_widget(label)

    def on_container_switch_in_event(self, ui):
        MeldDoc.on_container_switch_in_event(self, ui)
        self._create_filter_menu_button(ui)
        self.ui_manager = ui

    def on_container_switch_out_event(self, ui):
        self._cleanup_filter_menu_button(ui)
        MeldDoc.on_container_switch_out_event(self, ui)

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
            callback = functools.partial(self._update_name_filter, idx=i)
            actions.append((
                name, None, f.label, None, _("Hide %s") % f.label,
                callback, f.active
            ))
            self.filter_ui.append([
                "/CustomPopup", name, name,
                Gtk.UIManagerItemType.MENUITEM, False
            ])
            self.filter_ui.append([
                "/Menubar/ViewMenu/FileFilters", name, name,
                Gtk.UIManagerItemType.MENUITEM, False
            ])
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
        self._do_to_others(
            adjustment, adjs, "set_value", (int(adjustment.get_value()),))

    def _sync_hscroll(self, adjustment):
        adjs = [sw.get_hadjustment() for sw in self.scrolledwindow]
        self._do_to_others(
            adjustment, adjs, "set_value", (int(adjustment.get_value()),))

    def _get_focused_pane(self):
        for i, treeview in enumerate(self.treeview):
            if treeview.is_focus():
                return i
        return None

    def file_deleted(self, path, pane):
        # is file still extant in other pane?
        it = self.model.get_iter(path)
        files = self.model.value_paths(it)
        is_present = [os.path.exists(f) for f in files]
        if 1 in is_present:
            self._update_item_state(it)
        else:  # nope its gone
            self.model.remove(it)
        self._update_diffmaps()

    def file_created(self, path, pane):
        it = self.model.get_iter(path)
        root = Gtk.TreePath.new_first()
        while it and self.model.get_path(it) != root:
            self._update_item_state(it)
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
            if l and not isinstance(l, str):
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
            uris = [Gio.File.new_for_path(d)
                    for d in self.model.value_paths(root)]
        else:
            uris = []
        return RecentType.Folder, uris

    def recursively_update(self, path):
        """Recursively update from tree path 'path'.
        """
        it = self.model.get_iter(path)
        child = self.model.iter_children(it)
        while child:
            self.model.remove(child)
            child = self.model.iter_children(it)
        self._update_item_state(it)
        self._scan_in_progress += 1
        self.scheduler.add_task(self._search_recursively_iter(path))

    def _search_recursively_iter(self, rootpath):
        for t in self.treeview:
            sel = t.get_selection()
            sel.unselect_all()

        yield _("[%s] Scanning %s") % (self.label_text, "")
        prefixlen = 1 + len(
            self.model.value_path(self.model.get_iter(rootpath), 0))
        symlinks_followed = set()
        # TODO: This is horrible.
        if isinstance(rootpath, tuple):
            rootpath = Gtk.TreePath(rootpath)
        todo = [rootpath]
        expanded = set()

        shadowed_entries = []
        invalid_filenames = []
        while len(todo):
            todo.sort()  # depth first
            path = todo.pop(0)
            it = self.model.get_iter(path)
            roots = self.model.value_paths(it)

            # Buggy ordering when deleting rows means that we sometimes try to
            # recursively update files; this fix seems the least invasive.
            if not any(os.path.isdir(root) for root in roots):
                continue

            yield _("[%s] Scanning %s") % (
                self.label_text, roots[0][prefixlen:])
            differences = False
            encoding_errors = []

            canonicalize = None
            if self.actiongroup.get_action("IgnoreCase").get_active():
                canonicalize = CanonicalListing.canonicalize_lower
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
                        e.encode('utf8')
                    except UnicodeEncodeError:
                        invalid = e.encode('utf8', 'surrogatepass')
                        printable = invalid.decode('utf8', 'backslashreplace')
                        encoding_errors.append((pane, printable))
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
                    entries = [
                        os.path.join(r, n) for r, n in zip(roots, names)]
                    child = self.model.add_entries(it, entries)
                    differences |= self._update_item_state(child)
                    todo.append(self.model.get_path(child))
                for names in allfiles:
                    entries = [
                        os.path.join(r, n) for r, n in zip(roots, names)]
                    child = self.model.add_entries(it, entries)
                    differences |= self._update_item_state(child)
            else:
                # Our subtree is empty, or has been filtered to be empty
                if (tree.STATE_NORMAL in self.state_filters or
                        not all(os.path.isdir(f) for f in roots)):
                    self.model.add_empty(it)
                    if self.model.iter_parent(it) is None:
                        expanded.add(tree_path_as_tuple(rootpath))
                else:
                    # At this point, we have an empty folder tree node; we can
                    # prune this and any ancestors that then end up empty.
                    while not self.model.iter_has_child(it):
                        parent = self.model.iter_parent(it)

                        # In our tree, there is always a top-level parent with
                        # no siblings. If we're here, we have an empty tree.
                        if parent is None:
                            self.model.add_empty(it)
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
                expanded.add(tree_path_as_tuple(path))

        if invalid_filenames or shadowed_entries:
            self._show_tree_wide_errors(invalid_filenames, shadowed_entries)
        elif not expanded:
            self._show_identical_status()

        self.treeview[0].expand_to_path(Gtk.TreePath(("0",)))
        for path in sorted(expanded):
            self.treeview[0].expand_to_path(Gtk.TreePath(path))
        yield _("[%s] Done") % self.label_text

        self._scan_in_progress -= 1
        self.force_cursor_recalculate = True
        self.treeview[0].set_cursor(Gtk.TreePath.new_first())
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
            entry_str = _("“%s” hidden by “%s”") % (paths[0], paths[1])
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
                            primary=_("Replace folder “%s”?") % folder_name,
                            secondary=_(
                                "Another folder with the same name already "
                                "exists in “%s”.\n"
                                "If you replace the existing folder, all "
                                "files in it will be lost.") % parent_name,
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
                    _("Couldn’t copy %s\nto %s.\n\n%s") % (
                        GLib.markup_escape_text(src),
                        GLib.markup_escape_text(dst),
                        GLib.markup_escape_text(str(err)),
                    )
                )

    @with_focused_pane
    def delete_selected(self, pane):
        """Trash or delete all selected files/folders recursively"""

        paths = self._get_selected_paths(pane)

        # Reversing paths means that we remove tree rows bottom-up, so
        # tree paths don't change during the iteration.
        paths.reverse()
        for path in paths:
            it = self.model.get_iter(path)
            name = self.model.value_path(it, pane)
            gfile = Gio.File.new_for_path(name)

            try:
                deleted = trash_or_confirm(gfile)
            except Exception as e:
                misc.error_dialog(
                    _("Error deleting {}").format(
                        GLib.markup_escape_text(gfile.get_parse_name()),
                    ),
                    str(e),
                )
            else:
                if deleted:
                    self.file_deleted(path, pane)

    def on_treemodel_row_deleted(self, model, path):
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

            is_single_foldable_row = False
            if (selection.count_selected_rows() == 1):
                path = selection.get_selected_rows()[1][0]
                it = self.model.get_iter(path)
                is_single_foldable_row = self.model.iter_has_child(it)

            get_action("DirCompare").set_sensitive(True)
            get_action("DirCollapseRecursively").set_sensitive(
                is_single_foldable_row)
            get_action("DirExpandRecursively").set_sensitive(
                is_single_foldable_row)
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

        if self.force_cursor_recalculate:
            # We force cursor recalculation on initial load, and when
            # we handle model change events.
            skip = False
            self.force_cursor_recalculate = False
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
                if state not in (
                        tree.STATE_NORMAL, tree.STATE_NOCHANGE,
                        tree.STATE_EMPTY):
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
        return event.keyval in (Gdk.KEY_Left, Gdk.KEY_Right)  # handled

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
            self.emit("create-diff", [Gio.File.new_for_path(r)
                      for r in rows if os.path.isfile(r)], {})
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

    def on_treeview_focus_in_event(self, tree, event):
        self.focus_pane = tree
        pane = self.treeview.index(tree)
        self.on_treeview_selection_changed(tree.get_selection(), pane)
        tree.emit("cursor-changed")

    def run_diff_from_iter(self, it):
        row_paths = self.model.value_paths(it)
        gfiles = [Gio.File.new_for_path(p)
                  for p in row_paths if os.path.exists(p)]
        self.emit("create-diff", gfiles, {})

    def on_button_diff_clicked(self, button):
        pane = self._get_focused_pane()
        if pane is None:
            return

        selected = self._get_selected_paths(pane)
        for row in selected:
            self.run_diff_from_iter(self.model.get_iter(row))

    def on_collapse_recursive_clicked(self, action):
        pane = self._get_focused_pane()
        if pane is None:
            return

        root_path = self._get_selected_paths(pane)[0]
        filter_model = Gtk.TreeModelFilter(
            child_model=self.model, virtual_root=root_path)
        paths_to_collapse = []
        filter_model.foreach(self.append_paths_to_collapse, paths_to_collapse)
        paths_to_collapse.insert(0, root_path)

        for path in reversed(paths_to_collapse):
            self.treeview[pane].collapse_row(path)

    def append_paths_to_collapse(
            self, filter_model, filter_path, filter_iter, paths_to_collapse):
        path = filter_model.convert_path_to_child_path(filter_path)
        paths_to_collapse.append(path)

    def on_expand_recursive_clicked(self, action):
        pane = self._get_focused_pane()
        if pane is None:
            return

        paths = self._get_selected_paths(pane)
        for path in paths:
            self.treeview[pane].expand_row(path, True)

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
        files = [
            self.model.value_path(self.model.get_iter(p), pane)
            for p in self._get_selected_paths(pane)
        ]
        files = [f for f in files if f]
        if files:
            self._open_files(files)

    def on_button_ignore_case_toggled(self, button):
        self.refresh()

    def on_filter_state_toggled(self, button):
        active_filters = [
            state for state, (_, action_name) in self.state_actions.items()
            if self.actiongroup.get_action(action_name).get_active()
        ]

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
                self.model.remove(self.model.get_iter(p))

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
           Returns STATE_NORMAL, STATE_NOCHANGE, STATE_NEW or STATE_MODIFIED

               roots - array of root directories
               fileslist - array of filename tuples of length len(roots)
        """
        assert len(roots) == self.model.ntree
        ret = []
        regexes = [f.byte_filter for f in self.text_filters if f.active]
        for files in fileslist:
            curfiles = [os.path.join(r, f) for r, f in zip(roots, files)]
            is_present = [os.path.exists(f) for f in curfiles]
            all_present = 0 not in is_present
            if all_present:
                comparison_result = self.file_compare(curfiles, regexes)
                if comparison_result in (
                        Same, DodgySame):
                    state = tree.STATE_NORMAL
                elif comparison_result == SameFiltered:
                    state = tree.STATE_NOCHANGE
                else:
                    state = tree.STATE_MODIFIED
            else:
                state = tree.STATE_NEW
            # Always retain NORMAL folders for comparison; we remove these
            # later if they have no children.
            if (state in self.state_filters or
                    all(os.path.isdir(f) for f in curfiles)):
                ret.append(files)
        return ret

    def _update_item_state(self, it):
        """Update the state of a tree row

        All changes and updates to tree rows should happen here;
        structural changes happen elsewhere, but they only delete rows
        or add new rows with path information. This function is the
        only place where row details are changed.
        """
        files = self.model.value_paths(it)
        regexes = [f.byte_filter for f in self.text_filters if f.active]

        def none_stat(f):
            try:
                return os.stat(f)
            except OSError:
                return None
        stats = [none_stat(f) for f in files[:self.num_panes]]
        sizes = [s.st_size if s else 0 for s in stats]
        perms = [s.st_mode if s else 0 for s in stats]
        times = [s.st_mtime if s else 0 for s in stats]

        def none_lstat(f):
            try:
                return os.lstat(f)
            except OSError:
                return None

        lstats = [none_lstat(f) for f in files[:self.num_panes]]
        symlinks = {
            i for i, s in enumerate(lstats) if s and stat.S_ISLNK(s.st_mode)
        }

        def format_name_override(f):
            source = GLib.markup_escape_text(os.path.basename(f))
            target = GLib.markup_escape_text(os.readlink(f))
            return "{} ⟶ {}".format(source, target)

        name_overrides = [
            format_name_override(f) if i in symlinks else None
            for i, f in enumerate(files)
        ]

        existing_times = [s.st_mtime for s in stats if s]
        newest_time = max(existing_times) if existing_times else 0
        if existing_times.count(newest_time) == len(existing_times):
            # If all actually-present files have the same mtime, don't
            # pretend that any are "newer", and do the same if e.g.,
            # there's only one file.
            newest = set()
        else:
            newest = {i for i, t in enumerate(times) if t == newest_time}

        if all(stats):
            all_same = self.file_compare(files, regexes)
            all_present_same = all_same
        else:
            lof = [f for f, time in zip(files, times) if time]
            all_same = Different
            all_present_same = self.file_compare(lof, regexes)

        # TODO: Differentiate the DodgySame case
        if all_same == Same or all_same == DodgySame:
            state = tree.STATE_NORMAL
        elif all_same == SameFiltered:
            state = tree.STATE_NOCHANGE
        # TODO: Differentiate the SameFiltered and DodgySame cases
        elif all_present_same in (Same, SameFiltered, DodgySame):
            state = tree.STATE_NEW
        elif all_same == FileError or all_present_same == FileError:
            state = tree.STATE_ERROR
        # Different and DodgyDifferent
        else:
            state = tree.STATE_MODIFIED
        different = state not in {tree.STATE_NORMAL, tree.STATE_NOCHANGE}

        isdir = [os.path.isdir(files[j]) for j in range(self.model.ntree)]
        for j in range(self.model.ntree):
            if stats[j]:
                self.model.set_path_state(
                    it, j, state, isdir[j], display_text=name_overrides[j])
                emblem = EMBLEM_NEW if j in newest else None
                link_emblem = EMBLEM_SYMLINK if j in symlinks else None
                self.model.unsafe_set(it, j, {
                    COL_EMBLEM: emblem,
                    COL_EMBLEM_SECONDARY: link_emblem,
                    COL_TIME: times[j],
                    COL_PERMS: perms[j]
                })
                # Size is handled independently, because unsafe_set
                # can't correctly box GObject.TYPE_INT64.
                self.model.set(
                    it, self.model.column_index(COL_SIZE, j), sizes[j])
            else:
                self.model.set_path_state(
                    it, j, tree.STATE_NONEXIST, any(isdir))
                # SET time, size and perms to -1 since None of GInt is 0
                # TODO: change it to math.nan some day
                # https://gitlab.gnome.org/GNOME/glib/issues/183
                self.model.unsafe_set(it, j, {
                    COL_TIME: -1.0,
                    COL_SIZE: -1,
                    COL_PERMS: -1
                })
        return different

    def popup_in_pane(self, pane, event):
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
                row_states.append(
                    self.model.get_state(rowiter.iter, treeindex))
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

    def set_num_panes(self, num_panes):
        if num_panes == self.num_panes or num_panes not in (1, 2, 3):
            return

        self.model = DirDiffTreeStore(num_panes)
        self.model.connect("row-deleted", self.on_treemodel_row_deleted)
        for treeview in self.treeview:
            treeview.set_model(self.model)

        for (w, i) in zip(self.diffmap, (0, num_panes - 1)):
            scroll = self.scrolledwindow[i].get_vscrollbar()
            idx = 1 if i else 0
            w.setup(scroll, self.get_state_traversal(idx))

        for widget in (
                self.vbox[:num_panes] + self.file_toolbar[:num_panes] +
                self.diffmap[:num_panes] + self.linkmap[:num_panes - 1] +
                self.dummy_toolbar_linkmap[:num_panes - 1]):
            widget.show()

        for widget in (
                self.vbox[num_panes:] + self.file_toolbar[num_panes:] +
                self.diffmap[num_panes:] + self.linkmap[num_panes - 1:] +
                self.dummy_toolbar_linkmap[num_panes - 1:]):
            widget.hide()

        self.num_panes = num_panes

    def refresh(self):
        root = self.model.get_iter_first()
        if root:
            roots = self.model.value_paths(root)
            self.set_locations(roots)

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
            # search the tree one path part at a time
            for part in changed:
                child = model.iter_children(it)
                while child:
                    child_path = model.value_path(child, pane)
                    # Found the changed path
                    if child_path and part == os.path.basename(child_path):
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
            self._update_item_state(model.get_iter(path))
        self._update_diffmaps()
        self.force_cursor_recalculate = True

    def on_linkmap_scroll_event(self, linkmap, event):
        self.next_diff(event.direction)

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

    def auto_compare(self):
        modified_states = (tree.STATE_MODIFIED, tree.STATE_CONFLICT)
        for it in self.model.state_rows(modified_states):
            self.run_diff_from_iter(it)
