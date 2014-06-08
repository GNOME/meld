# coding=UTF-8

# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2010-2013 Kai Willadsen <kai.willadsen@gmail.com>
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

from . import melddoc
from . import misc
from . import recent
from . import tree
from . import vc
from .ui import emblemcellrenderer
from .ui import gnomeglade
from .ui import vcdialogs

from meld.conf import _
from meld.settings import settings, bind_settings
from meld.vc import _null

log = logging.getLogger(__name__)


def _commonprefix(files):
    if len(files) != 1:
        workdir = misc.commonprefix(files)
    else:
        workdir = os.path.dirname(files[0]) or "."
    return workdir


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


COL_LOCATION, COL_STATUS, COL_REVISION, COL_OPTIONS, COL_END = \
    list(range(tree.COL_END, tree.COL_END + 5))


class VcTreeStore(tree.DiffTreeStore):
    def __init__(self):
        tree.DiffTreeStore.__init__(self, 1, [str] * 5)

################################################################################
# filters
################################################################################
entry_modified = lambda x: (x.state >= tree.STATE_NEW) or (x.isdir and (x.state > tree.STATE_NONE))
entry_normal   = lambda x: (x.state == tree.STATE_NORMAL)
entry_nonvc    = lambda x: (x.state == tree.STATE_NONE) or (x.isdir and (x.state > tree.STATE_IGNORED))
entry_ignored  = lambda x: (x.state == tree.STATE_IGNORED) or x.isdir


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

    # Map action names to VC commands and required arguments list
    action_vc_cmds_map = {
        "VcCommit": ("commit_command", ("",)),
        "VcUpdate": ("update_command", ()),
        "VcPush": ("push", (lambda *args, **kwargs: None, )),
        "VcAdd": ("add_command", ()),
        "VcResolved": ("resolved_command", ()),
        "VcRemove": ("remove_command", ()),
        "VcRevert": ("revert_command", ()),
    }

    # Map for inter-tab command() calls
    command_map = {
        'resolve': 'resolve',
    }

    state_actions = {
        "flatten": ("VcFlatten", None),
        "modified": ("VcShowModified", entry_modified),
        "normal": ("VcShowNormal", entry_normal),
        "unknown": ("VcShowNonVC", entry_nonvc),
        "ignored": ("VcShowIgnored", entry_ignored),
    }

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
        selection = self.treeview.get_selection()
        selection.set_mode(Gtk.SelectionMode.MULTIPLE)
        selection.connect("changed", self.on_treeview_selection_changed)
        self.treeview.set_headers_visible(1)
        self.treeview.set_search_equal_func(
            self.model.treeview_search_cb, None)
        self.current_path, self.prev_path, self.next_path = None, None, None

        self.column_name_map = {}
        col_index = self.model.column_index
        column = Gtk.TreeViewColumn(_("Name"))
        column.set_resizable(True)
        renicon = emblemcellrenderer.EmblemCellRenderer()
        column.pack_start(renicon, False)
        column.set_attributes(renicon,
                              icon_name=col_index(tree.COL_ICON, 0),
                              icon_tint=col_index(tree.COL_TINT, 0))
        rentext = Gtk.CellRendererText()
        column.pack_start(rentext, True)
        column.set_attributes(rentext,
                              text=col_index(tree.COL_TEXT, 0),
                              foreground=col_index(tree.COL_FG, 0),
                              style=col_index(tree.COL_STYLE, 0),
                              weight=col_index(tree.COL_WEIGHT, 0),
                              strikethrough=col_index(tree.COL_STRIKE, 0))
        column_index = self.treeview.append_column(column) - 1
        self.column_name_map[vc.DATA_NAME] = column_index

        def addCol(name, num, data_name=None):
            column = Gtk.TreeViewColumn(name)
            column.set_resizable(True)
            rentext = Gtk.CellRendererText()
            column.pack_start(rentext, True)
            column.set_attributes(rentext,
                                  markup=self.model.column_index(num, 0))
            column_index = self.treeview.append_column(column) - 1
            if data_name:
                self.column_name_map[data_name] = column_index
            return column

        self.treeview_column_location = addCol(_("Location"), COL_LOCATION)
        addCol(_("Status"), COL_STATUS, vc.DATA_STATE)
        addCol(_("Revision"), COL_REVISION, vc.DATA_REVISION)
        addCol(_("Options"), COL_OPTIONS, vc.DATA_OPTIONS)

        self.consolestream = ConsoleStream(self.consoleview)
        self.location = None
        self.treeview_column_location.set_visible(self.actiongroup.get_action("VcFlatten").get_active())
        self.vc = None
        self.valid_vc_actions = tuple()

        cell = Gtk.CellRendererText()
        self.combobox_vcs.pack_start(cell, False)
        self.combobox_vcs.add_attribute(cell, 'text', 0)
        self.combobox_vcs.add_attribute(cell, 'sensitive', 2)
        self.combobox_vcs.lock = False

        settings.bind('vc-console-visible',
                      self.actiongroup.get_action('VcConsoleVisible'),
                      'active', Gio.SettingsBindFlags.DEFAULT)
        settings.bind('vc-console-visible', self.console_vbox, 'visible',
                      Gio.SettingsBindFlags.DEFAULT)
        settings.bind('vc-console-pane-position', self.vc_console_vpaned,
                      'position', Gio.SettingsBindFlags.DEFAULT)

        self.state_filters = []
        for s in self.state_actions:
            if s in self.props.status_filters:
                action_name = self.state_actions[s][0]
                self.state_filters.append(s)
                self.actiongroup.get_action(action_name).set_active(True)

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

    def update_visible_columns(self):
        for data_id in self.column_name_map:
            col = self.treeview.get_column(self.column_name_map[data_id])
            col.set_visible(data_id in self.vc.VC_COLUMNS)

    def update_actions_sensitivity(self):
        """Disable actions that use not implemented VC plugin methods"""
        valid_vc_actions = ["VcDeleteLocally"]
        for action_name, (meth_name, args) in self.action_vc_cmds_map.items():
            action = self.actiongroup.get_action(action_name)
            try:
                getattr(self.vc, meth_name)(*args)
                action.props.sensitive = True
                valid_vc_actions.append(action_name)
            except NotImplementedError:
                action.props.sensitive = False
        self.valid_vc_actions = tuple(valid_vc_actions)

    def choose_vc(self, location):
        """Display VC plugin(s) that can handle the location"""
        self.combobox_vcs.lock = True
        vcs_model = self.combobox_vcs.get_model()
        vcs_model.clear()
        default_active = -1
        valid_vcs = []
        location = os.path.abspath(location or ".")

        # VC systems work at the directory level, so make sure we're checking
        # for VC support there instead of on a specific file.
        if os.path.isfile(location):
            location = os.path.dirname(location)
        vcs = vc.get_vcs(location)
        # Try to keep the same VC plugin active on refresh()
        for idx, avc in enumerate(vcs):
            # See if the necessary version control command exists.  If so,
            # make sure what we're diffing is a valid respository.  If either
            # check fails don't let the user select the that version control
            # tool and display a basic error message in the drop-down menu.
            err_str = ""

            if not avc.is_installed():
                # TRANSLATORS: this is an error message when a version control
                # application isn't installed or can't be found
                err_str = _("%s not installed" % avc.CMD)
            elif not avc.valid_repo(location):
                # TRANSLATORS: this is an error message when a version
                # controlled repository is invalid or corrupted
                err_str = _("Invalid repository")
            else:
                valid_vcs.append(idx)
                if (self.vc is not None and
                        self.vc.__class__ == avc.__class__):
                    default_active = idx

            if err_str:
                vcs_model.append(
                    [_("%s (%s)") % (avc.NAME, err_str), avc, False])
            else:
                name = avc.NAME or _("None")
                vcs_model.append([name, avc(location), True])

        if not valid_vcs:
            # If we didn't get any valid vcs then fallback to null
            null_vcs = _null.Vc(location)
            vcs.append(null_vcs)
            vcs_model.insert(
                0, [_("None"), null_vcs, True])
            default_active = 0

        if default_active == -1:
            if valid_vcs:
                default_active = min(valid_vcs)
            else:
                default_active = 0

        # If we only have the null VC, give a better error message.
        if (len(vcs) == 1 and not vcs[0].CMD) or (len(valid_vcs) == 0):
            tooltip = _("No valid version control system found in this folder")
        elif len(vcs) == 1:
            tooltip = _("Only one version control system found in this folder")
        else:
            tooltip = _("Choose which version control system to use")

        self.combobox_vcs.set_tooltip_text(tooltip)
        self.combobox_vcs.set_sensitive(len(vcs) > 1)
        self.combobox_vcs.lock = False
        self.combobox_vcs.set_active(default_active)

    def on_vc_change(self, cb):
        if not cb.lock:
            self.vc = cb.get_model()[cb.get_active_iter()][1]
            self._set_location(self.vc.location)
            self.update_actions_sensitivity()
            self.update_visible_columns()

    def set_location(self, location):
        self.choose_vc(location)

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

        # If the user is just diffing a file (ie not a directory), there's no
        # need to scan the rest of the repository
        if os.path.isdir(self.vc.location):
            root = self.model.get_iter_first()

            try:
                col = self.model.column_index(COL_OPTIONS, 0)
                self.model.set_value(root, col,
                                     self.vc.get_commits_to_push_summary())
            except NotImplementedError:
                pass

            self.scheduler.add_task(self._search_recursively_iter(root))
            self.scheduler.add_task(self.on_treeview_selection_changed)
            self.scheduler.add_task(self.on_treeview_cursor_changed)

    def get_comparison(self):
        return recent.TYPE_VC, [self.location]

    def recompute_label(self):
        location = self.location
        if isinstance(location, str):
            location = location.decode(
                sys.getfilesystemencoding(), 'replace')
        self.label_text = os.path.basename(location)
        # TRANSLATORS: This is the location of the directory the user is diffing
        self.tooltip_text = _("%s: %s") % (_("Location"), location)
        self.label_changed()

    def _search_recursively_iter(self, iterstart):
        rootname = self.model.value_path(iterstart, 0)
        prefixlen = len(self.location) + 1
        symlinks_followed = set()
        todo = [(self.model.get_path(iterstart), rootname)]

        flattened = self.actiongroup.get_action("VcFlatten").get_active()
        active_action = lambda a: self.actiongroup.get_action(a).get_active()
        filters = [a[1] for a in self.state_actions.values() if
                   active_action(a[0]) and a[1]]

        yield _("Scanning %s") % rootname
        self.vc.cache_inventory(rootname)
        while todo:
            # This needs to happen sorted and depth-first in order for our row
            # references to remain valid while we traverse.
            todo.sort()
            treepath, path = todo.pop(0)
            it = self.model.get_iter(treepath)
            yield _("Scanning %s") % path[prefixlen:]

            entries = self.vc.listdir(path)
            entries = [e for e in entries if any(f(e) for f in filters)]
            for e in entries:
                if e.isdir and e.state != tree.STATE_REMOVED:
                    try:
                        st = os.lstat(e.path)
                    # Covers certain unreadable symlink cases; see bgo#585895
                    except OSError as err:
                        error_string = "%s: %s" % (e.path, err.strerror)
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
                                self._update_item_state(child, e, path[prefixlen:])
                            todo.append((Gtk.TreePath.new_first(), e.path))
                        continue

                child = self.model.add_entries(it, [e.path])
                if e.isdir and e.state != tree.STATE_IGNORED:
                    todo.append((self.model.get_path(child), e.path))
                self._update_item_state(child, e, path[prefixlen:])

            if flattened:
                root = Gtk.TreePath.new_first()
                self.treeview.expand_row(Gtk.TreePath(root), False)
            else:
                if not entries:
                    self.model.add_empty(it, _("(Empty)"))
                if any(e.state != tree.STATE_NORMAL for e in entries):
                    self.treeview.expand_to_path(treepath)

    # TODO: This doesn't fire when the user selects a shortcut folder
    def on_fileentry_file_set(self, fileentry):
        directory = fileentry.get_file()
        path = directory.get_path()
        self.set_location(path)

    def on_delete_event(self, appquit=0):
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
            path = self.model.value_path(it, 0)
            if not self.model.is_folder(it, 0, path):
                self.run_diff(path)

    def run_diff(self, path):
        if os.path.isdir(path):
            self.emit("create-diff", [path], {})
            return

        left_is_local = self.props.left_is_local
        basename = os.path.basename(path)
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
            if left_is_local:
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

    def on_treeview_popup_menu(self, treeview):
        time = Gtk.get_current_event_time()
        self.popup_menu.popup(None, None, None, None, 0, time)
        return True

    def on_button_press_event(self, treeview, event):
        if event.button == 3:
            path = treeview.get_path_at_pos(int(event.x), int(event.y))
            if path is None:
                return False
            selection = treeview.get_selection()
            model, rows = selection.get_selected_rows()

            if path[0] not in rows:
                selection.unselect_all()
                selection.select_path(path[0])
                treeview.set_cursor(path[0])

            self.popup_menu.popup(None, None, None, None, event.button,
                                  event.time)
            return True
        return False

    def on_button_flatten_toggled(self, button):
        action = self.actiongroup.get_action("VcFlatten")
        self.treeview_column_location.set_visible(action.get_active())
        self.on_filter_state_toggled(button)

    def on_filter_state_toggled(self, button):
        active_action = lambda a: self.actiongroup.get_action(a).get_active()
        active_filters = [a for a in self.state_actions if
                          active_action(self.state_actions[a][0])]

        if set(active_filters) == set(self.state_filters):
            return

        self.state_filters = active_filters
        self.props.status_filters = active_filters
        self.refresh()

    def on_treeview_selection_changed(self, selection=None):

        def set_sensitive(action, sensitive):
            self.actiongroup.get_action(action).set_sensitive(sensitive)

        if selection is None:
            selection = self.treeview.get_selection()
        model, rows = selection.get_selected_rows()
        if hasattr(self.vc, 'update_actions_for_paths'):
            paths = [self.model.value_path(model.get_iter(r), 0) for r in rows]
            states = [self.model.get_state(model.get_iter(r), 0) for r in rows]
            action_sensitivity = {
                "VcCompare": False,
                "VcCommit": False,
                "VcUpdate": False,
                "VcPush": False,
                "VcAdd": False,
                "VcResolved": False,
                "VcRemove": False,
                "VcRevert": False,
                "VcDeleteLocally": bool(paths) and self.vc.root not in paths,
            }
            path_states = dict(zip(paths, states))
            self.vc.update_actions_for_paths(path_states, action_sensitivity)
            for action, sensitivity in action_sensitivity.items():
                set_sensitive(action, sensitivity)
        else:
            have_selection = bool(rows)
            for action in self.valid_vc_actions:
                set_sensitive(action, have_selection)

    def _get_selected_files(self):
        model, rows = self.treeview.get_selection().get_selected_rows()
        sel = [self.model.value_path(self.model.get_iter(r), 0) for r in rows]
        # Remove empty entries and trailing slashes
        return [x[-1] != "/" and x or x[:-1] for x in sel if x is not None]

    def _command_iter(self, command, files, refresh, working_dir=None):
        """Run 'command' on 'files'. Return a tuple of the directory the
           command was executed in and the output of the command.
        """

        def shelljoin(command):
            def quote(s):
                return '"%s"' % s if len(s.split()) > 1 else s
            return " ".join(quote(tok) for tok in command)

        msg = shelljoin(command)
        yield "[%s] %s" % (self.label_text, msg.replace("\n", "\t"))
        def relpath(pbase, p):
            kill = 0
            if len(pbase) and p.startswith(pbase):
                kill = len(pbase) + 1
            return p[kill:] or "."
        if working_dir:
            workdir = self.vc.get_working_directory(working_dir)
        elif len(files) == 1 and os.path.isdir(files[0]):
            workdir = self.vc.get_working_directory(files[0])
        else:
            workdir = self.vc.get_working_directory(_commonprefix(files))
        files = [relpath(workdir, f) for f in files]
        r = None
        self.consolestream.command(shelljoin(command + files) + " (in %s)\n" % workdir)
        readiter = misc.read_pipe_iter(command + files, self.consolestream,
                                       workdir=workdir)
        try:
            while r is None:
                r = next(readiter)
                self.consolestream.output(r)
                yield 1
        except IOError as err:
            misc.error_dialog(
                "Error running command",
                "While running '%s'\nError: %s" % (msg, err))
        self.consolestream.output("\n")

        returncode = next(readiter)
        if returncode:
            self.console_vbox.show()

        if refresh:
            self.refresh_partial(workdir)
        yield workdir, r

    def has_command(self, command):
        return command in self.command_map

    def command(self, command, files):
        if not self.has_command(command):
            log.error("Couldn't understand command %s", command)

        if not isinstance(files, list):
            log.error("Invalid files argument to '%s': %r", command, files)

        command = getattr(self.vc, self.command_map[command])
        command(self._command, files)

    def _command(self, command, files, refresh=1, working_dir=None):
        """Run 'command' on 'files'.
        """
        self.scheduler.add_task(self._command_iter(command, files, refresh,
                                                   working_dir))

    def _command_on_selected(self, command, refresh=1):
        files = self._get_selected_files()
        if len(files):
            self._command(command, files, refresh)

    def on_button_update_clicked(self, obj):
        try:
            self.vc.update(self._command, self._get_selected_files())
        except NotImplementedError:
            self._command_on_selected(self.vc.update_command())

    def on_button_push_clicked(self, obj):
        vcdialogs.PushDialog(self).run()

    def on_button_commit_clicked(self, obj):
        vcdialogs.CommitDialog(self).run()

    def on_button_add_clicked(self, obj):
        try:
            self.vc.add(self._command, self._get_selected_files())
        except NotImplementedError:
            self._command_on_selected(self.vc.add_command())

    def on_button_remove_clicked(self, obj):
        selected = self._get_selected_files()
        if any(os.path.isdir(p) for p in selected):
            # TODO: Improve and reuse this dialog for the non-VC delete action
            dialog = Gtk.MessageDialog(
                parent=self.widget.get_toplevel(),
                flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
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

        try:
            self.vc.remove(self._command, selected)
        except NotImplementedError:
            self._command_on_selected(self.vc.remove_command())

    def on_button_resolved_clicked(self, obj):
        try:
            self.vc.resolve(self._command, self._get_selected_files())
        except NotImplementedError:
            self._command_on_selected(self.vc.resolved_command())

    def on_button_revert_clicked(self, obj):
        try:
            self.vc.revert(self._command, self._get_selected_files())
        except NotImplementedError:
            self._command_on_selected(self.vc.revert_command())

    def on_button_delete_clicked(self, obj):
        files = self._get_selected_files()
        for name in files:
            try:
                gfile = Gio.File.new_for_path(name)
                gfile.trash(None)
            except GLib.GError as e:
                misc.error_dialog(_("Error removing %s") % name, str(e))
        workdir = _commonprefix(files)
        self.refresh_partial(workdir)

    def on_button_diff_clicked(self, obj):
        files = self._get_selected_files()
        for f in files:
            self.run_diff(f)

    def open_external(self):
        self._open_files(self._get_selected_files())

    def refresh(self):
        self.set_location(self.model.value_path(self.model.get_iter_first(), 0))

    def refresh_partial(self, where):
        if not self.actiongroup.get_action("VcFlatten").get_active():
            it = self.find_iter_by_name(where)
            if it:
                newiter = self.model.insert_after(None, it)
                self.model.set_value(
                    newiter, self.model.column_index(tree.COL_PATH, 0), where)
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

    def _update_item_state(self, it, vcentry, location):
        e = vcentry
        self.model.set_path_state(it, 0, e.state, e.isdir)

        def setcol(col, val):
            self.model.set_value(it, self.model.column_index(col, 0), val)
        setcol(COL_LOCATION, location)
        setcol(COL_STATUS, e.get_status())
        setcol(COL_REVISION, e.rev)
        setcol(COL_OPTIONS, e.options)

    def on_file_changed(self, filename):
        it = self.find_iter_by_name(filename)
        if it:
            path = self.model.value_path(it, 0)
            self.vc.update_file_state(path)
            files = self.vc.lookup_files([], [(os.path.basename(path), path)])[1]
            for e in files:
                if e.path == path:
                    prefixlen = 1 + len( self.model.value_path( self.model.get_iter_first(), 0 ) )
                    self._update_item_state( it, e, e.parent[prefixlen:])
                    return

    def find_iter_by_name(self, name):
        it = self.model.get_iter_first()
        path = self.model.value_path(it, 0)
        while it:
            if name == path:
                return it
            elif name.startswith(path):
                child = self.model.iter_children( it )
                while child:
                    path = self.model.value_path(child, 0)
                    if name == path:
                        return child
                    elif name.startswith(path):
                        break
                    else:
                        child = self.model.iter_next( child )
                it = child
            else:
                break
        return None

    def on_consoleview_populate_popup(self, textview, menu):
        buf = textview.get_buffer()
        clear_cb = lambda *args: buf.delete(*buf.get_bounds())
        clear_action = Gtk.ImageMenuItem(Gtk.STOCK_CLEAR)
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
