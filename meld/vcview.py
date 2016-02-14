# coding=UTF-8

# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2010-2015 Kai Willadsen <kai.willadsen@gmail.com>
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

from __future__ import print_function

import atexit
import functools
import logging
import tempfile
import shutil
import os
import stat
import sys

from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import Gio
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango

from meld import melddoc
from meld import misc
from meld import recent
from meld import tree
from meld import vc
from meld.ui import gnomeglade
from meld.ui import vcdialogs

from meld.conf import _
from meld.settings import settings, bind_settings
from meld.vc import _null
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
        except:
            except_str = "{0[0]}: \"{0[1]}\"".format(sys.exc_info())
            print("File \"{0}\" not removed due to".format(f), except_str,
                  file=sys.stderr)
    for f in _temp_dirs:
        try:
            assert (os.path.exists(f) and os.path.isabs(f) and
                    os.path.dirname(f) == temp_location)
            shutil.rmtree(f, ignore_errors=1)
        except:
            except_str = "{0[0]}: \"{0[1]}\"".format(sys.exc_info())
            print("Directory \"{0}\" not removed due to".format(f), except_str,
                  file=sys.stderr)

_temp_dirs, _temp_files = [], []
atexit.register(cleanup_temp)


class ConsoleStream(object):

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
        tree.DiffTreeStore.__init__(self, 1, [str] * 5)

    def get_file_path(self, it):
        # Use instead of value_path; does not incorrectly decode
        return self.get_value(it, self.column_index(tree.COL_PATH, 0))


class VcView(melddoc.MeldDoc, gnomeglade.Component):

    __gtype_name__ = "VcView"

    __gsettings_bindings__ = (
        ('vc-status-filters', 'status-filters'),
        ('vc-left-is-local', 'left-is-local'),
        ('vc-merge-file-order', 'merge-file-order'),
    )

    status_filters = GObject.property(
        type=GObject.TYPE_STRV,
        nick="File status filters",
        blurb="Files with these statuses will be shown by the comparison.",
    )
    left_is_local = GObject.property(type=bool, default=False)
    merge_file_order = GObject.property(type=str, default="local-merge-remote")

    # Map for inter-tab command() calls
    command_map = {
        'resolve': 'resolve',
    }

    state_actions = {
        "flatten": ("VcFlatten", None),
        "modified": ("VcShowModified", Entry.is_modified),
        "normal": ("VcShowNormal", Entry.is_normal),
        "unknown": ("VcShowNonVC", Entry.is_nonvc),
        "ignored": ("VcShowIgnored", Entry.is_ignored),
    }

    file_encoding = sys.getfilesystemencoding()

    @classmethod
    def display_path(cls, bytes):
        encodings = (cls.file_encoding,)
        return misc.fallback_decode(bytes, encodings, lossy=True)

    def __init__(self):
        melddoc.MeldDoc.__init__(self)
        gnomeglade.Component.__init__(self, "vcview.ui", "vcview",
                                      ["VcviewActions", 'liststore_vcs'])
        bind_settings(self)

        self.ui_file = gnomeglade.ui_file("vcview-ui.xml")
        self.actiongroup = self.VcviewActions
        self.actiongroup.set_translation_domain("meld")
        self.model = VcTreeStore()
        self.widget.connect("style-updated", self.model.on_style_updated)
        self.model.on_style_updated(self.widget)
        self.treeview.set_model(self.model)
        self.treeview.get_selection().connect(
            "changed", self.on_treeview_selection_changed)
        self.treeview.set_search_equal_func(
            self.model.treeview_search_cb, None)
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
        self.location_column.bind_property(
            'visible', self.actiongroup.get_action("VcFlatten"), 'active')

        self.consolestream = ConsoleStream(self.consoleview)
        self.location = None
        self.vc = None

        settings.bind('vc-console-visible',
                      self.actiongroup.get_action('VcConsoleVisible'),
                      'active', Gio.SettingsBindFlags.DEFAULT)
        settings.bind('vc-console-visible', self.console_vbox, 'visible',
                      Gio.SettingsBindFlags.DEFAULT)
        settings.bind('vc-console-pane-position', self.vc_console_vpaned,
                      'position', Gio.SettingsBindFlags.DEFAULT)

        for s in self.props.status_filters:
            if s in self.state_actions:
                self.actiongroup.get_action(
                    self.state_actions[s][0]).set_active(True)

    def _set_external_action_sensitivity(self, focused):
        try:
            self.main_actiongroup.get_action("OpenExternal").set_sensitive(
                focused)
        except AttributeError:
            pass

    def on_container_switch_in_event(self, ui):
        super(VcView, self).on_container_switch_in_event(ui)
        self._set_external_action_sensitivity(True)
        self.scheduler.add_task(self.on_treeview_cursor_changed)

    def on_container_switch_out_event(self, ui):
        self._set_external_action_sensitivity(False)
        super(VcView, self).on_container_switch_out_event(ui)

    def populate_vcs_for_location(self, location):
        """Display VC plugin(s) that can handle the location"""
        vcs_model = self.combobox_vcs.get_model()
        vcs_model.clear()

        # VC systems work at the directory level, so make sure we're checking
        # for VC support there instead of on a specific file.
        location = os.path.abspath(location or ".")
        if os.path.isfile(location):
            location = os.path.dirname(location)

        for avc in vc.get_vcs(location):
            err_str = ''
            vc_details = {'name': avc.NAME, 'cmd': avc.CMD}

            if not avc.is_installed():
                # Translators: This error message is shown when a version
                # control binary isn't installed.
                err_str = _("%(name)s (%(cmd)s not installed)")
            elif not avc.valid_repo(location):
                # Translators: This error message is shown when a version
                # controlled repository is invalid.
                err_str = _("%(name)s (Invalid repository)")

            if err_str:
                vcs_model.append([err_str % vc_details, avc, False])
                continue

            vcs_model.append([avc.NAME, avc(location), True])

        valid_vcs = [(i, r[1].NAME) for i, r in enumerate(vcs_model) if r[2]]
        default_active = min(valid_vcs)[0] if valid_vcs else 0

        # Keep the same VC plugin active on refresh, otherwise use the first
        current_vc_name = self.vc.NAME if self.vc else None
        same_vc = [i for i, name in valid_vcs if name == current_vc_name]
        if same_vc:
            default_active = same_vc[0]

        if not valid_vcs:
            # If we didn't get any valid vcs then fallback to null
            null_vcs = _null.Vc(location)
            vcs_model.insert(0, [null_vcs.NAME, null_vcs, True])
            tooltip = _("No valid version control system found in this folder")
        elif len(vcs_model) == 1:
            tooltip = _("Only one version control system found in this folder")
        else:
            tooltip = _("Choose which version control system to use")

        self.combobox_vcs.set_tooltip_text(tooltip)
        self.combobox_vcs.set_sensitive(len(vcs_model) > 1)
        self.combobox_vcs.set_active(default_active)

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
        self.fileentry.set_filename(location)
        it = self.model.add_entries(None, [location])
        self.treeview.grab_focus()
        self.treeview.get_selection().select_iter(it)
        self.model.set_path_state(it, 0, tree.STATE_NORMAL, isdir=1)
        self.recompute_label()
        self.scheduler.remove_all_tasks()

        # If the user is just diffing a file (i.e., not a directory),
        # there's no need to scan the rest of the repository.
        if not os.path.isdir(self.vc.location):
            return

        root = self.model.get_iter_first()

        try:
            self.model.set_value(
                root, COL_OPTIONS, self.vc.get_commits_to_push_summary())
        except NotImplementedError:
            pass

        self.scheduler.add_task(self.vc.refresh_vc_state)
        self.scheduler.add_task(self._search_recursively_iter(root))
        self.scheduler.add_task(self.on_treeview_selection_changed)
        self.scheduler.add_task(self.on_treeview_cursor_changed)

    def get_comparison(self):
        return recent.TYPE_VC, [self.location]

    def recompute_label(self):
        location = self.display_path(self.location)
        self.label_text = os.path.basename(location)
        # TRANSLATORS: This is the location of the directory being viewed
        self.tooltip_text = _("%s: %s") % (_("Location"), location)
        self.label_changed()

    def _search_recursively_iter(self, iterstart):
        rootname = self.model.get_file_path(iterstart)
        display_prefix = len(self.display_path(rootname)) + 1
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
            yield _("Scanning %s") % self.display_path(path)[display_prefix:]

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

    # TODO: This doesn't fire when the user selects a shortcut folder
    def on_fileentry_file_set(self, fileentry):
        directory = fileentry.get_file()
        path = directory.get_path()
        self.set_location(path)

    def on_delete_event(self):
        self.scheduler.remove_all_tasks()
        self.emit('close', 0)
        return Gtk.ResponseType.OK

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
            self.emit("create-diff", [path], {})
            return

        basename = self.display_path(os.path.basename(path))
        meta = {
            'parent': self,
            'prompt_resolve': False,
        }

        # May have removed directories in list.
        vc_entry = self.vc.get_entry(path)
        if vc_entry and vc_entry.state == tree.STATE_CONFLICT and \
                hasattr(self.vc, 'get_path_for_conflict'):
            local_label = _(u"%s — local") % basename
            remote_label = _(u"%s — remote") % basename

            # We create new temp files for other, base and this, and
            # then set the output to the current file.
            if self.props.merge_file_order == "local-merge-remote":
                conflicts = (tree.CONFLICT_THIS, tree.CONFLICT_MERGED,
                             tree.CONFLICT_OTHER)
                meta['labels'] = (local_label, None, remote_label)
                meta['tablabel'] = _(u"%s (local, merge, remote)") % basename
            else:
                conflicts = (tree.CONFLICT_OTHER, tree.CONFLICT_MERGED,
                             tree.CONFLICT_THIS)
                meta['labels'] = (remote_label, None, local_label)
                meta['tablabel'] = _(u"%s (remote, merge, local)") % basename
            diffs = [self.vc.get_path_for_conflict(path, conflict=c)
                     for c in conflicts]
            temps = [p for p, is_temp in diffs if is_temp]
            diffs = [p for p, is_temp in diffs]
            kwargs = {
                'auto_merge': False,
                'merge_output': path,
            }
            meta['prompt_resolve'] = True
        else:
            remote_label = _(u"%s — repository") % basename
            comp_path = self.vc.get_path_for_repo_file(path)
            temps = [comp_path]
            if self.props.left_is_local:
                diffs = [path, comp_path]
                meta['labels'] = (None, remote_label)
                meta['tablabel'] = _(u"%s (working, repository)") % basename
            else:
                diffs = [comp_path, path]
                meta['labels'] = (remote_label, None)
                meta['tablabel'] = _(u"%s (repository, working)") % basename
            kwargs = {}
        kwargs['meta'] = meta

        for temp_file in temps:
            os.chmod(temp_file, 0o444)
            _temp_files.append(temp_file)

        self.emit("create-diff", diffs, kwargs)

    def do_popup_treeview_menu(self, widget, event):
        if event:
            button = event.button
            time = event.time
        else:
            button = 0
            time = Gtk.get_current_event_time()
        self.popup_menu.popup(None, None, None, None, button, time)

    def on_treeview_popup_menu(self, treeview):
        self.do_popup_treeview_menu(treeview, None)
        return True

    def on_button_press_event(self, treeview, event):
        if (event.triggers_context_menu() and
                event.type == Gdk.EventType.BUTTON_PRESS):
            path = treeview.get_path_at_pos(int(event.x), int(event.y))
            if path is None:
                return False
            selection = treeview.get_selection()
            model, rows = selection.get_selected_rows()

            if path[0] not in rows:
                selection.unselect_all()
                selection.select_path(path[0])
                treeview.set_cursor(path[0])

            self.do_popup_treeview_menu(treeview, event)
            return True
        return False

    def on_filter_state_toggled(self, button):
        active_action = lambda a: self.actiongroup.get_action(a).get_active()
        active_filters = [
            k for k, v in self.state_actions.items() if active_action(v[0])]

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
            "VcCompare": 'compare' in valid_actions,
            "VcCommit": 'commit' in valid_actions,
            "VcUpdate": 'update' in valid_actions,
            "VcPush": 'push' in valid_actions,
            "VcAdd": 'add' in valid_actions,
            "VcResolved": 'resolve' in valid_actions,
            "VcRemove": 'remove' in valid_actions,
            "VcRevert": 'revert' in valid_actions,
            "VcDeleteLocally": bool(paths) and self.vc.root not in paths,
        }
        for action, sensitivity in action_sensitivity.items():
            self.actiongroup.get_action(action).set_sensitive(sensitivity)

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
        readiter = misc.read_pipe_iter(
            command + files, workdir=working_dir,
            errorstream=self.consolestream)
        try:
            result = next(readiter)
            while not result:
                yield 1
                result = next(readiter)
        except IOError as err:
            misc.error_dialog(
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

    def command(self, command, files):
        if not self.has_command(command):
            log.error("Couldn't understand command %s", command)
            return

        if not isinstance(files, list):
            log.error("Invalid files argument to '%s': %r", command, files)
            return

        command = getattr(self.vc, self.command_map[command])
        command(self.runner, files)

    def runner(self, command, files, refresh, working_dir):
        """Schedule a version control command to run as an idle task"""
        self.scheduler.add_task(
            self._command_iter(command, files, refresh, working_dir))

    def on_button_update_clicked(self, obj):
        self.vc.update(self.runner)

    def on_button_push_clicked(self, obj):
        response = vcdialogs.PushDialog(self).run()
        if response == Gtk.ResponseType.OK:
            self.vc.push(self.runner)

    def on_button_commit_clicked(self, obj):
        response, commit_msg = vcdialogs.CommitDialog(self).run()
        if response == Gtk.ResponseType.OK:
            self.vc.commit(
                self.runner, self._get_selected_files(), commit_msg)

    def on_button_add_clicked(self, obj):
        self.vc.add(self.runner, self._get_selected_files())

    def on_button_remove_clicked(self, obj):
        selected = self._get_selected_files()
        if any(os.path.isdir(p) for p in selected):
            # TODO: Improve and reuse this dialog for the non-VC delete action
            dialog = Gtk.MessageDialog(
                parent=self.widget.get_toplevel(),
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

    def on_button_resolved_clicked(self, obj):
        self.vc.resolve(self.runner, self._get_selected_files())

    def on_button_revert_clicked(self, obj):
        self.vc.revert(self.runner, self._get_selected_files())

    def on_button_delete_clicked(self, obj):
        files = self._get_selected_files()
        for name in files:
            try:
                gfile = Gio.File.new_for_path(name)
                gfile.trash(None)
            except GLib.GError as e:
                misc.error_dialog(_("Error removing %s") % name, str(e))

        workdir = os.path.dirname(os.path.commonprefix(files))
        self.refresh_partial(workdir)

    def on_button_diff_clicked(self, obj):
        files = self._get_selected_files()
        for f in files:
            self.run_diff(f)

    def open_external(self):
        self._open_files(self._get_selected_files())

    def refresh(self):
        root = self.model.get_iter_first()
        if root is None:
            return
        self.set_location(self.model.get_file_path(root))

    def refresh_partial(self, where):
        if not self.actiongroup.get_action("VcFlatten").get_active():
            it = self.find_iter_by_name(where)
            if it:
                newiter = self.model.insert_after(None, it)
                self.model.set_value(
                    newiter, tree.COL_PATH, where)
                self.model.set_path_state(newiter, 0, tree.STATE_NORMAL, True)
                self.model.remove(it)
                self.treeview.grab_focus()
                self.treeview.get_selection().select_iter(newiter)
                self.scheduler.add_task(self._search_recursively_iter(newiter))
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

    def on_consoleview_populate_popup(self, textview, menu):
        buf = textview.get_buffer()
        clear_cb = lambda *args: buf.delete(*buf.get_bounds())
        clear_action = Gtk.MenuItem.new_with_label(_("Clear"))
        clear_action.connect("activate", clear_cb)
        menu.insert(clear_action, 0)
        menu.insert(Gtk.SeparatorMenuItem(), 1)
        menu.show_all()

    def on_treeview_cursor_changed(self, *args):
        cursor_path, cursor_col = self.treeview.get_cursor()
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

    def next_diff(self, direction):
        if direction == Gdk.ScrollDirection.UP:
            path = self.prev_path
        else:
            path = self.next_path
        if path:
            self.treeview.expand_to_path(path)
            self.treeview.set_cursor(path)

    def on_refresh_activate(self, *extra):
        self.on_fileentry_file_set(self.fileentry)

    def on_find_activate(self, *extra):
        self.treeview.emit("start-interactive-search")
