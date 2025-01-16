# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2010-2019 Kai Willadsen <kai.willadsen@gmail.com>
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

import atexit
import functools
import logging
import os
import shutil
import stat
import sys
import tempfile
from typing import Tuple

from gi.repository import Gdk, Gio, GLib, GObject, Gtk, Pango

from meld import tree
from meld.conf import _
from meld.externalhelpers import open_files_external
from meld.iohelpers import trash_or_confirm
from meld.melddoc import MeldDoc
from meld.misc import error_dialog, read_pipe_iter
from meld.recent import RecentType
from meld.settings import bind_settings, settings
from meld.ui.vcdialogs import CommitDialog, PushDialog
from meld.vc import _null, get_vcs
from meld.vc._vc import Entry

log = logging.getLogger(__name__)


def cleanup_temp():
    temp_location = tempfile.gettempdir()
    # The strings below will probably end up as debug log, and are deliberately
    # not marked for translation.
    for f in _temp_files:
        try:
            assert (os.path.exists(f) and os.path.isabs(f) and
                    os.path.dirname(f) == temp_location)
            # Windows throws permissions errors if we remove read-only files
            if os.name == "nt":
                os.chmod(f, stat.S_IWRITE)
            os.remove(f)
        except Exception:
            except_str = "{0[0]}: \"{0[1]}\"".format(sys.exc_info())
            print("File \"{0}\" not removed due to".format(f), except_str,
                  file=sys.stderr)
    for f in _temp_dirs:
        try:
            assert (os.path.exists(f) and os.path.isabs(f) and
                    os.path.dirname(f) == temp_location)
            shutil.rmtree(f, ignore_errors=1)
        except Exception:
            except_str = "{0[0]}: \"{0[1]}\"".format(sys.exc_info())
            print("Directory \"{0}\" not removed due to".format(f), except_str,
                  file=sys.stderr)


_temp_dirs, _temp_files = [], []
atexit.register(cleanup_temp)


class ConsoleStream:

    def __init__(self, textview):
        self.textview = textview
        buf = textview.get_buffer()
        self.command_tag = buf.create_tag("command")
        self.command_tag.props.weight = Pango.Weight.BOLD
        self.output_tag = buf.create_tag("output")
        self.error_tag = buf.create_tag("error")
        # FIXME: Need to add this to the gtkrc?
        self.error_tag.props.foreground = "#cc0000"
        self.end_mark = buf.create_mark(None, buf.get_end_iter(),
                                        left_gravity=False)

    def command(self, message):
        self.write(message, self.command_tag)

    def output(self, message):
        self.write(message, self.output_tag)

    def error(self, message):
        self.write(message, self.error_tag)

    def write(self, message, tag):
        if not message:
            return
        buf = self.textview.get_buffer()
        buf.insert_with_tags(buf.get_end_iter(), message, tag)
        self.textview.scroll_mark_onscreen(self.end_mark)


COL_LOCATION, COL_STATUS, COL_OPTIONS, COL_END = \
    list(range(tree.COL_END, tree.COL_END + 4))


class VcTreeStore(tree.DiffTreeStore):
    def __init__(self):
        super().__init__(1, [str] * 5)

    def get_file_path(self, it):
        return self.get_value(it, self.column_index(tree.COL_PATH, 0))


@Gtk.Template(resource_path='/org/gnome/meld/ui/vcview.ui')
class VcView(Gtk.Box, tree.TreeviewCommon, MeldDoc):

    __gtype_name__ = "VcView"

    __gsettings_bindings__ = (
        ('vc-status-filters', 'status-filters'),
        ('vc-left-is-local', 'left-is-local'),
        ('vc-merge-file-order', 'merge-file-order'),
    )

    close_signal = MeldDoc.close_signal
    create_diff_signal = MeldDoc.create_diff_signal
    file_changed_signal = MeldDoc.file_changed_signal
    label_changed = MeldDoc.label_changed
    move_diff = MeldDoc.move_diff
    tab_state_changed = MeldDoc.tab_state_changed

    status_filters = GObject.Property(
        type=GObject.TYPE_STRV,
        nick="File status filters",
        blurb="Files with these statuses will be shown by the comparison.",
    )
    left_is_local = GObject.Property(type=bool, default=False)
    merge_file_order = GObject.Property(type=str, default="local-merge-remote")

    # Map for inter-tab command() calls
    command_map = {
        'resolve': 'resolve',
    }

    state_actions = {
        'flatten': ('vc-flatten', None),
        'modified': ('vc-status-modified', Entry.is_modified),
        'normal': ('vc-status-normal', Entry.is_normal),
        'unknown': ('vc-status-unknown', Entry.is_nonvc),
        'ignored': ('vc-status-ignored', Entry.is_ignored),
    }

    replaced_entries = (
        # Remove Ctrl+Page Up/Down bindings. These are used to do horizontal
        # scrolling in GTK by default, but we preference easy tab switching.
        (Gdk.KEY_Page_Up, Gdk.ModifierType.CONTROL_MASK),
        (Gdk.KEY_KP_Page_Up, Gdk.ModifierType.CONTROL_MASK),
        (Gdk.KEY_Page_Down, Gdk.ModifierType.CONTROL_MASK),
        (Gdk.KEY_KP_Page_Down, Gdk.ModifierType.CONTROL_MASK),
    )

    combobox_vcs = Gtk.Template.Child()
    console_vbox = Gtk.Template.Child()
    consoleview = Gtk.Template.Child()
    emblem_renderer = Gtk.Template.Child()
    extra_column = Gtk.Template.Child()
    extra_renderer = Gtk.Template.Child()
    filelabel = Gtk.Template.Child()
    liststore_vcs = Gtk.Template.Child()
    location_column = Gtk.Template.Child()
    location_renderer = Gtk.Template.Child()
    name_column = Gtk.Template.Child()
    name_renderer = Gtk.Template.Child()
    status_column = Gtk.Template.Child()
    status_renderer = Gtk.Template.Child()
    treeview = Gtk.Template.Child()
    vc_console_vpaned = Gtk.Template.Child()

    def __init__(self):
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

        binding_set_names = ("GtkScrolledWindow", "GtkTreeView")
        for set_name in binding_set_names:
            binding_set = Gtk.binding_set_find(set_name)
            for key, modifiers in self.replaced_entries:
                Gtk.binding_entry_remove(binding_set, key, modifiers)

        # Set up per-view action group for top-level menu insertion
        self.view_action_group = Gio.SimpleActionGroup()

        property_actions = (
            ('vc-console-visible', self.console_vbox, 'visible'),
        )
        for action_name, obj, prop_name in property_actions:
            action = Gio.PropertyAction.new(action_name, obj, prop_name)
            self.view_action_group.add_action(action)

        # Manually handle GAction additions
        actions = (
            ('compare', self.action_diff),
            ('find', self.action_find),
            ('next-change', self.action_next_change),
            ('open-external', self.action_open_external),
            ('previous-change', self.action_previous_change),
            ('refresh', self.action_refresh),
            ('vc-add', self.action_add),
            ('vc-unstage', self.action_unstage),
            ('vc-commit', self.action_commit),
            ('vc-delete-locally', self.action_delete),
            ('vc-push', self.action_push),
            ('vc-remove', self.action_remove),
            ('vc-resolve', self.action_resolved),
            ('vc-revert', self.action_revert),
            ('vc-update', self.action_update),
        )
        for name, callback in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', callback)
            self.view_action_group.add_action(action)

        new_boolean = GLib.Variant.new_boolean
        stateful_actions = (
            ('vc-filter', None, GLib.Variant.new_boolean(False)),
            ('vc-flatten', self.action_filter_state_change,
                new_boolean('flatten' in self.props.status_filters)),
            ('vc-status-modified', self.action_filter_state_change,
                new_boolean('modified' in self.props.status_filters)),
            ('vc-status-normal', self.action_filter_state_change,
                new_boolean('normal' in self.props.status_filters)),
            ('vc-status-unknown', self.action_filter_state_change,
                new_boolean('unknown' in self.props.status_filters)),
            ('vc-status-ignored', self.action_filter_state_change,
                new_boolean('ignored' in self.props.status_filters)),
        )
        for (name, callback, state) in stateful_actions:
            action = Gio.SimpleAction.new_stateful(name, None, state)
            if callback:
                action.connect('change-state', callback)
            self.view_action_group.add_action(action)

        builder = Gtk.Builder.new_from_resource(
            '/org/gnome/meld/ui/vcview-menus.ui')
        context_menu = builder.get_object('vcview-context-menu')
        self.popup_menu = Gtk.Menu.new_from_model(context_menu)
        self.popup_menu.attach_to_widget(self)

        self.model = VcTreeStore()
        self.treeview.set_model(self.model)
        self.treeview.get_selection().connect(
            "changed", self.on_treeview_selection_changed)
        self.treeview.set_search_equal_func(tree.treeview_search_cb, None)
        self.current_path, self.prev_path, self.next_path = None, None, None

        self.name_column.set_attributes(
            self.emblem_renderer,
            icon_name=tree.COL_ICON,
            icon_tint=tree.COL_TINT)
        self.name_column.set_attributes(
            self.name_renderer,
            text=tree.COL_TEXT,
            foreground_rgba=tree.COL_FG,
            style=tree.COL_STYLE,
            weight=tree.COL_WEIGHT,
            strikethrough=tree.COL_STRIKE)
        self.location_column.set_attributes(
            self.location_renderer, markup=COL_LOCATION)
        self.status_column.set_attributes(
            self.status_renderer, markup=COL_STATUS)
        self.extra_column.set_attributes(
            self.extra_renderer, markup=COL_OPTIONS)

        self.consolestream = ConsoleStream(self.consoleview)
        self.location = None
        self.vc = None

        settings.bind('vc-console-visible', self.console_vbox, 'visible',
                      Gio.SettingsBindFlags.DEFAULT)
        settings.bind('vc-console-pane-position', self.vc_console_vpaned,
                      'position', Gio.SettingsBindFlags.DEFAULT)

    def on_container_switch_in_event(self, window):
        super().on_container_switch_in_event(window)
        # FIXME: open-external should be tied to having a treeview selection
        self.set_action_enabled("open-external", True)
        self.scheduler.add_task(self.on_treeview_cursor_changed)

    def on_container_switch_out_event(self, window):
        self.set_action_enabled("open-external", False)
        super().on_container_switch_out_event(window)

    def get_default_vc(self, vcs):
        target_name = self.vc.NAME if self.vc else None

        for i, (name, vc, enabled) in enumerate(vcs):
            if not enabled:
                continue

            if target_name and name == target_name:
                return i

        depths = [len(getattr(vc, 'root', [])) for name, vc, enabled in vcs]
        target_depth = max(depths, default=0)

        for i, (name, vc, enabled) in enumerate(vcs):
            if not enabled:
                continue

            if target_depth and len(vc.root) == target_depth:
                return i

        return 0

    def populate_vcs_for_location(self, location):
        """Display VC plugin(s) that can handle the location"""
        vcs_model = self.combobox_vcs.get_model()
        vcs_model.clear()

        # VC systems can be executed at the directory level, so make sure
        # we're checking for VC support there instead of
        # on a specific file or on deleted/unexisting path inside vc
        location = os.path.abspath(location or ".")
        while not os.path.isdir(location):
            parent_location = os.path.dirname(location)
            if len(parent_location) >= len(location):
                # no existing parent: for example unexisting drive on Windows
                break
            location = parent_location
        else:
            # existing parent directory was found
            for avc, enabled in get_vcs(location):
                err_str = ''
                vc_details = {'name': avc.NAME, 'cmd': avc.CMD}

                if not enabled:
                    # Translators: This error message is shown when no
                    # repository of this type is found.
                    err_str = _("%(name)s (not found)")
                elif not avc.is_installed():
                    # Translators: This error message is shown when a version
                    # control binary isn't installed.
                    err_str = _("%(name)s (%(cmd)s not installed)")
                elif not avc.valid_repo(location):
                    # Translators: This error message is shown when a version
                    # controlled repository is invalid.
                    err_str = _("%(name)s (invalid repository)")

                if err_str:
                    vcs_model.append([err_str % vc_details, avc, False])
                    continue

                vcs_model.append([avc.NAME, avc(location), True])

        default_active = self.get_default_vc(vcs_model)

        if not any(enabled for _, _, enabled in vcs_model):
            # If we didn't get any valid vcs then fallback to null
            null_vcs = _null.Vc(location)
            vcs_model.insert(0, [null_vcs.NAME, null_vcs, True])
            tooltip = _("No valid version control system found in this folder")
        else:
            tooltip = _("Choose which version control system to use")

        self.combobox_vcs.set_tooltip_text(tooltip)
        self.combobox_vcs.set_active(default_active)

    @Gtk.Template.Callback()
    def on_vc_change(self, combobox_vcs):
        active_iter = combobox_vcs.get_active_iter()
        if active_iter is None:
            return
        self.vc = combobox_vcs.get_model()[active_iter][1]
        self._set_location(self.vc.location)

    def set_location(self, location):
        self.populate_vcs_for_location(location)

    def _set_location(self, location):
        self.location = location
        self.current_path = None
        self.model.clear()
        self.filelabel.props.gfile = Gio.File.new_for_path(location)
        it = self.model.add_entries(None, [location])
        self.treeview.get_selection().select_iter(it)
        self.model.set_path_state(it, 0, tree.STATE_NORMAL, isdir=1)
        self.recompute_label()
        self.scheduler.remove_all_tasks()

        # If the user is just diffing a file (i.e., not a directory),
        # there's no need to scan the rest of the repository.
        if not os.path.isdir(self.vc.location):
            return

        root = self.model.get_iter_first()
        root_path = self.model.get_path(root)

        try:
            self.model.set_value(
                root, COL_OPTIONS, self.vc.get_commits_to_push_summary())
        except NotImplementedError:
            pass

        self.scheduler.add_task(self.vc.refresh_vc_state)
        self.scheduler.add_task(self._search_recursively_iter(root_path))
        self.scheduler.add_task(self.on_treeview_selection_changed)
        self.scheduler.add_task(self.on_treeview_cursor_changed)

    def get_comparison(self):
        if self.location:
            uris = [Gio.File.new_for_path(self.location)]
        else:
            uris = []
        return RecentType.VersionControl, uris

    def recompute_label(self):
        self.label_text = os.path.basename(self.location)
        self.tooltip_text = "\n".join((
            # TRANSLATORS: This is the name of the version control
            # system being used, e.g., "Git" or "Subversion"
            _("{vc} comparison:").format(vc=self.vc.NAME),
            self.location,
        ))
        self.label_changed.emit(self.label_text, self.tooltip_text)

    def set_labels(self, labels):
        if labels:
            self.filelabel.custom_label = labels[0]

        self.recompute_label()

    def _search_recursively_iter(self, start_path, replace=False):

        # Initial yield so when we add this to our tasks, we don't
        # create iterators that may be invalidated.
        yield _("Scanning repository")

        if replace:
            # Replace the row at start_path with a new, empty row ready
            # to be filled.
            old_iter = self.model.get_iter(start_path)
            file_path = self.model.get_file_path(old_iter)
            new_iter = self.model.insert_after(None, old_iter)
            self.model.set_value(new_iter, tree.COL_PATH, file_path)
            self.model.set_path_state(new_iter, 0, tree.STATE_NORMAL, True)
            self.model.remove(old_iter)

        iterstart = self.model.get_iter(start_path)
        rootname = self.model.get_file_path(iterstart)
        display_prefix = len(rootname) + 1
        symlinks_followed = set()
        todo = [(self.model.get_path(iterstart), rootname)]

        flattened = 'flatten' in self.props.status_filters
        active_actions = [
            self.state_actions.get(k) for k in self.props.status_filters]
        filters = [a[1] for a in active_actions if a and a[1]]

        while todo:
            # This needs to happen sorted and depth-first in order for our row
            # references to remain valid while we traverse.
            todo.sort()
            treepath, path = todo.pop(0)
            it = self.model.get_iter(treepath)
            yield _("Scanning %s") % path[display_prefix:]

            entries = self.vc.get_entries(path)
            entries = [e for e in entries if any(f(e) for f in filters)]
            entries = sorted(entries, key=lambda e: e.name)
            entries = sorted(entries, key=lambda e: not e.isdir)
            for e in entries:
                if e.isdir and e.is_present():
                    try:
                        st = os.lstat(e.path)
                    # Covers certain unreadable symlink cases; see bgo#585895
                    except OSError as err:
                        error_string = "%r: %s" % (e.path, err.strerror)
                        self.model.add_error(it, error_string, 0)
                        continue

                    if stat.S_ISLNK(st.st_mode):
                        key = (st.st_dev, st.st_ino)
                        if key in symlinks_followed:
                            continue
                        symlinks_followed.add(key)

                    if flattened:
                        if e.state != tree.STATE_IGNORED:
                            # If directory state is changed, render it in
                            # in flattened mode.
                            if e.state != tree.STATE_NORMAL:
                                child = self.model.add_entries(it, [e.path])
                                self._update_item_state(child, e)
                            todo.append((Gtk.TreePath.new_first(), e.path))
                        continue

                child = self.model.add_entries(it, [e.path])
                if e.isdir and e.state != tree.STATE_IGNORED:
                    todo.append((self.model.get_path(child), e.path))
                self._update_item_state(child, e)

            if not flattened:
                if not entries:
                    self.model.add_empty(it, _("(Empty)"))
                elif any(e.state != tree.STATE_NORMAL for e in entries):
                    self.treeview.expand_to_path(treepath)

        self.treeview.expand_row(Gtk.TreePath.new_first(), False)
        self.treeview.set_cursor(Gtk.TreePath.new_first())

    # TODO: This doesn't fire when the user selects a shortcut folder
    @Gtk.Template.Callback()
    def on_file_selected(
            self, button: Gtk.Button, pane: int, file: Gio.File) -> None:

        path = file.get_path()
        self.set_location(path)

    def on_delete_event(self):
        self.scheduler.remove_all_tasks()
        self.close_signal.emit(0)
        return Gtk.ResponseType.OK

    @Gtk.Template.Callback()
    def on_row_activated(self, treeview, path, tvc):
        it = self.model.get_iter(path)
        if self.model.iter_has_child(it):
            if self.treeview.row_expanded(path):
                self.treeview.collapse_row(path)
            else:
                self.treeview.expand_row(path, False)
        else:
            path = self.model.get_file_path(it)
            if not self.model.is_folder(it, 0, path):
                self.run_diff(path)

    def run_diff(self, path):
        if os.path.isdir(path):
            self.create_diff_signal.emit([Gio.File.new_for_path(path)], {})
            return

        basename = os.path.basename(path)
        meta = {
            'parent': self,
            'prompt_resolve': False,
        }

        # May have removed directories in list.
        vc_entry = self.vc.get_entry(path)
        if vc_entry and vc_entry.state == tree.STATE_CONFLICT and \
                hasattr(self.vc, 'get_path_for_conflict'):
            local_label = _("%s — local") % basename
            remote_label = _("%s — remote") % basename

            # We create new temp files for other, base and this, and
            # then set the output to the current file.
            if self.props.merge_file_order == "local-merge-remote":
                conflicts = (tree.CONFLICT_THIS, tree.CONFLICT_MERGED,
                             tree.CONFLICT_OTHER)
                meta['labels'] = (local_label, None, remote_label)
                meta['tablabel'] = _("%s (local, merge, remote)") % basename
            else:
                conflicts = (tree.CONFLICT_OTHER, tree.CONFLICT_MERGED,
                             tree.CONFLICT_THIS)
                meta['labels'] = (remote_label, None, local_label)
                meta['tablabel'] = _("%s (remote, merge, local)") % basename
            diffs = [self.vc.get_path_for_conflict(path, conflict=c)
                     for c in conflicts]
            temps = [p for p, is_temp in diffs if is_temp]
            diffs = [p for p, is_temp in diffs]
            kwargs = {
                'auto_merge': False,
                'merge_output': Gio.File.new_for_path(path),
            }
            meta['prompt_resolve'] = True
        else:
            remote_label = _("%s — repository") % basename
            comp_path = self.vc.get_path_for_repo_file(path)
            temps = [comp_path]
            if self.props.left_is_local:
                diffs = [path, comp_path]
                meta['labels'] = (None, remote_label)
                meta['tablabel'] = _("%s (working, repository)") % basename
            else:
                diffs = [comp_path, path]
                meta['labels'] = (remote_label, None)
                meta['tablabel'] = _("%s (repository, working)") % basename
            kwargs = {}
        kwargs['meta'] = meta

        for temp_file in temps:
            os.chmod(temp_file, 0o444)
            _temp_files.append(temp_file)

        self.create_diff_signal.emit(
            [Gio.File.new_for_path(d) for d in diffs],
            kwargs,
        )

    def get_filter_visibility(self) -> Tuple[bool, bool, bool]:
        return False, False, True

    def action_filter_state_change(self, action, value):
        action.set_state(value)

        active_filters = [
            k for k, (action_name, fn) in self.state_actions.items()
            if self.get_action_state(action_name)
        ]

        if set(active_filters) == set(self.props.status_filters):
            return

        self.props.status_filters = active_filters
        self.refresh()

    def on_treeview_selection_changed(self, selection=None):
        if selection is None:
            selection = self.treeview.get_selection()
        model, rows = selection.get_selected_rows()
        paths = [self.model.get_file_path(model.get_iter(r)) for r in rows]
        states = [self.model.get_state(model.get_iter(r), 0) for r in rows]
        path_states = dict(zip(paths, states))

        valid_actions = self.vc.get_valid_actions(path_states)
        action_sensitivity = {
            'compare': 'compare' in valid_actions,
            'vc-add': 'add' in valid_actions,
            'vc-unstage': 'unstage' in valid_actions,
            'vc-commit': 'commit' in valid_actions,
            'vc-delete-locally': bool(paths) and self.vc.root not in paths,
            'vc-push': 'push' in valid_actions,
            'vc-remove': 'remove' in valid_actions,
            'vc-resolve': 'resolve' in valid_actions,
            'vc-revert': 'revert' in valid_actions,
            'vc-update': 'update' in valid_actions,
        }
        for action, sensitivity in action_sensitivity.items():
            self.set_action_enabled(action, sensitivity)

    def _get_selected_files(self):
        model, rows = self.treeview.get_selection().get_selected_rows()
        sel = [self.model.get_file_path(self.model.get_iter(r)) for r in rows]
        # Remove empty entries and trailing slashes
        return [x[-1] != "/" and x or x[:-1] for x in sel if x is not None]

    def _command_iter(self, command, files, refresh, working_dir):
        """An iterable that runs a VC command on a set of files

        This method is intended to be used as a scheduled task, with
        standard out and error output displayed in this view's
        consolestream.
        """

        def shelljoin(command):
            def quote(s):
                return '"%s"' % s if len(s.split()) > 1 else s
            return " ".join(quote(tok) for tok in command)

        files = [os.path.relpath(f, working_dir) for f in files]
        msg = shelljoin(command + files) + " (in %s)\n" % working_dir
        self.consolestream.command(msg)
        readiter = read_pipe_iter(
            command + files, workdir=working_dir,
            errorstream=self.consolestream)
        try:
            result = next(readiter)
            while not result:
                yield 1
                result = next(readiter)
        except IOError as err:
            error_dialog(
                "Error running command",
                "While running '%s'\nError: %s" % (msg, err))
            result = (1, "")

        returncode, output = result
        self.consolestream.output(output + "\n")

        if returncode:
            self.console_vbox.show()

        if refresh:
            refresh = functools.partial(self.refresh_partial, working_dir)
            GLib.idle_add(refresh)

    def has_command(self, command):
        vc_command = self.command_map.get(command)
        return vc_command and hasattr(self.vc, vc_command)

    def command(self, command, files, sync=False):
        """
        Run a command against this view's version control subsystem

        This is the intended way for things outside of the VCView to
        call in to version control methods, e.g., to mark a conflict as
        resolved from a file comparison.

        :param command: The version control command to run, taken from
            keys in `VCView.command_map`.
        :param files: File parameters to the command as paths
        :param sync: If True, the command will be executed immediately
            (as opposed to being run by the idle scheduler).
        """
        if not self.has_command(command):
            log.error("Couldn't understand command %s", command)
            return

        if not isinstance(files, list):
            log.error("Invalid files argument to '%s': %r", command, files)
            return

        runner = self.runner if not sync else self.sync_runner
        command = getattr(self.vc, self.command_map[command])
        command(runner, files)

    def runner(self, command, files, refresh, working_dir):
        """Schedule a version control command to run as an idle task"""
        self.scheduler.add_task(
            self._command_iter(command, files, refresh, working_dir))

    def sync_runner(self, command, files, refresh, working_dir):
        """Run a version control command immediately"""
        for it in self._command_iter(command, files, refresh, working_dir):
            pass

    def action_update(self, *args):
        self.vc.update(self.runner)

    def action_push(self, *args):
        response = PushDialog(self).run()
        if response == Gtk.ResponseType.OK:
            self.vc.push(self.runner)

    def action_commit(self, *args):
        response, commit_msg = CommitDialog(self).run()
        if response == Gtk.ResponseType.OK:
            self.vc.commit(
                self.runner, self._get_selected_files(), commit_msg)

    def action_add(self, *args):
        self.vc.add(self.runner, self._get_selected_files())

    def action_unstage(self, *args):
        self.vc.unstage(self.runner, self._get_selected_files())

    def action_remove(self, *args):
        selected = self._get_selected_files()
        if any(os.path.isdir(p) for p in selected):
            # TODO: Improve and reuse this dialog for the non-VC delete action
            dialog = Gtk.MessageDialog(
                parent=self.get_toplevel(),
                flags=(Gtk.DialogFlags.MODAL |
                       Gtk.DialogFlags.DESTROY_WITH_PARENT),
                type=Gtk.MessageType.WARNING,
                message_format=_("Remove folder and all its files?"))
            dialog.format_secondary_text(
                _("This will remove all selected files and folders, and all "
                  "files within any selected folders, from version control."))

            dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
            dialog.add_button(_("_Remove"), Gtk.ResponseType.OK)
            response = dialog.run()
            dialog.destroy()
            if response != Gtk.ResponseType.OK:
                return

        self.vc.remove(self.runner, selected)

    def action_resolved(self, *args):
        self.vc.resolve(self.runner, self._get_selected_files())

    def action_revert(self, *args):
        self.vc.revert(self.runner, self._get_selected_files())

    def action_delete(self, *args):
        files = self._get_selected_files()
        for name in files:
            gfile = Gio.File.new_for_path(name)

            try:
                trash_or_confirm(gfile)
            except Exception as e:
                error_dialog(
                    _("Error deleting {}").format(
                        GLib.markup_escape_text(gfile.get_parse_name()),
                    ),
                    str(e),
                )

        workdir = os.path.dirname(os.path.commonprefix(files))
        self.refresh_partial(workdir)

    def action_diff(self, *args):
        # TODO: Review the compare/diff action. It doesn't really add much
        # over activate, since the folder compare doesn't work and hasn't
        # for... a long time.
        files = self._get_selected_files()
        for f in files:
            self.run_diff(f)

    def action_open_external(self, *args):
        gfiles = [Gio.File.new_for_path(f) for f in self._get_selected_files() if f]
        open_files_external(gfiles)

    def refresh(self):
        root = self.model.get_iter_first()
        if root is None:
            return
        self.set_location(self.model.get_file_path(root))

    def refresh_partial(self, where):
        if not self.get_action_state('vc-flatten'):
            it = self.find_iter_by_name(where)
            if not it:
                return
            path = self.model.get_path(it)

            self.treeview.grab_focus()
            self.vc.refresh_vc_state(where)
            self.scheduler.add_task(
                self._search_recursively_iter(path, replace=True))
            self.scheduler.add_task(self.on_treeview_selection_changed)
            self.scheduler.add_task(self.on_treeview_cursor_changed)
        else:
            # XXX fixme
            self.refresh()

    def _update_item_state(self, it, entry):
        self.model.set_path_state(it, 0, entry.state, entry.isdir)

        location = Gio.File.new_for_path(self.vc.location)
        parent = Gio.File.new_for_path(entry.path).get_parent()
        display_location = location.get_relative_path(parent)

        self.model.set_value(it, COL_LOCATION, display_location)
        self.model.set_value(it, COL_STATUS, entry.get_status())
        self.model.set_value(it, COL_OPTIONS, entry.options)

    def on_file_changed(self, filename):
        it = self.find_iter_by_name(filename)
        if it:
            path = self.model.get_file_path(it)
            self.vc.refresh_vc_state(path)
            entry = self.vc.get_entry(path)
            self._update_item_state(it, entry)

    def find_iter_by_name(self, name):
        it = self.model.get_iter_first()
        path = self.model.get_file_path(it)
        while it:
            if name == path:
                return it
            elif name.startswith(path):
                child = self.model.iter_children(it)
                while child:
                    path = self.model.get_file_path(child)
                    if name == path:
                        return child
                    elif name.startswith(path):
                        break
                    else:
                        child = self.model.iter_next(child)
                it = child
            else:
                break
        return None

    @Gtk.Template.Callback()
    def on_consoleview_populate_popup(self, textview, menu):
        buf = textview.get_buffer()
        clear_action = Gtk.MenuItem.new_with_label(_("Clear"))
        clear_action.connect(
            "activate", lambda *args: buf.delete(*buf.get_bounds()))
        menu.insert(clear_action, 0)
        menu.insert(Gtk.SeparatorMenuItem(), 1)
        menu.show_all()

    @Gtk.Template.Callback()
    def on_treeview_popup_menu(self, treeview):
        return tree.TreeviewCommon.on_treeview_popup_menu(self, treeview)

    @Gtk.Template.Callback()
    def on_treeview_button_press_event(self, treeview, event):
        return tree.TreeviewCommon.on_treeview_button_press_event(
            self, treeview, event)

    @Gtk.Template.Callback()
    def on_treeview_cursor_changed(self, *args):
        cursor_path, cursor_col = self.treeview.get_cursor()
        if not cursor_path:
            self.set_action_enabled("previous-change", False)
            self.set_action_enabled("next-change", False)
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
            prev, next_ = self.model._find_next_prev_diff(cursor_path)
            self.prev_path, self.next_path = prev, next_
            self.set_action_enabled("previous-change", prev is not None)
            self.set_action_enabled("next-change", next_ is not None)
        self.current_path = cursor_path

    def next_diff(self, direction):
        if direction == Gdk.ScrollDirection.UP:
            path = self.prev_path
        else:
            path = self.next_path
        if path:
            self.treeview.expand_to_path(path)
            self.treeview.set_cursor(path)
        else:
            self.error_bell()

    def action_previous_change(self, *args):
        self.next_diff(Gdk.ScrollDirection.UP)

    def action_next_change(self, *args):
        self.next_diff(Gdk.ScrollDirection.DOWN)

    def action_refresh(self, *args):
        self.set_location(self.location)

    def action_find(self, *args):
        self.treeview.emit("start-interactive-search")

    def auto_compare(self):
        modified_states = (tree.STATE_MODIFIED, tree.STATE_CONFLICT)
        for it in self.model.state_rows(modified_states):
            row_paths = self.model.value_paths(it)
            paths = [p for p in row_paths if os.path.exists(p)]
            self.run_diff(paths[0])


VcView.set_css_name('meld-vc-view')
