### Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
### Copyright (C) 2010-2012 Kai Willadsen <kai.willadsen@gmail.com>

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

from __future__ import print_function

import atexit
import tempfile
import shutil
import os
import sys
from gettext import gettext as _

import gtk
import pango

from . import melddoc
from . import misc
from . import paths
from . import recent
from . import tree
from . import vc
from .ui import emblemcellrenderer
from .ui import gnomeglade

################################################################################
#
# Local Functions
#
################################################################################

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
            assert os.path.exists(f) and os.path.isabs(f) and \
                   os.path.dirname(f) == temp_location
            os.remove(f)
        except:
            except_str = "{0[0]}: \"{0[1]}\"".format(sys.exc_info())
            print("File \"{0}\" not removed due to".format(f), except_str,
                  file=sys.stderr)
    for f in _temp_dirs:
        try:
            assert os.path.exists(f) and os.path.isabs(f) and \
                   os.path.dirname(f) == temp_location
            shutil.rmtree(f, ignore_errors=1)
        except:
            except_str = "{0[0]}: \"{0[1]}\"".format(sys.exc_info())
            print("Directory \"{0}\" not removed due to".format(f), except_str,
                  file=sys.stderr)

_temp_dirs, _temp_files = [], []
atexit.register(cleanup_temp)


################################################################################
#
# CommitDialog
#
################################################################################
class CommitDialog(gnomeglade.Component):
    def __init__(self, parent):
        gnomeglade.Component.__init__(self, paths.ui_dir("vcview.ui"), "commitdialog")
        self.parent = parent
        self.widget.set_transient_for( parent.widget.get_toplevel() )
        selected = parent._get_selected_files()
        topdir = _commonprefix(selected)
        selected = [ s[len(topdir):] for s in selected ]
        self.changedfiles.set_text( ("(in %s) "%topdir) + " ".join(selected) )
        self.widget.show_all()

    def run(self):
        self.previousentry.child.set_editable(False)
        self.previousentry.set_active(0)
        self.textview.grab_focus()
        buf = self.textview.get_buffer()
        buf.place_cursor( buf.get_start_iter() )
        buf.move_mark( buf.get_selection_bound(), buf.get_end_iter() )
        response = self.widget.run()
        msg = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), 0)
        if response == gtk.RESPONSE_OK:
            self.parent._command_on_selected( self.parent.vc.commit_command(msg) )
        if len(msg.strip()):
            self.previousentry.prepend_text(msg)
        self.widget.destroy()
    def on_previousentry_activate(self, gentry):
        buf = self.textview.get_buffer()
        buf.set_text( gentry.child.get_text() )

COL_LOCATION, COL_STATUS, COL_REVISION, COL_TAG, COL_OPTIONS, COL_END = \
    list(range(tree.COL_END, tree.COL_END+6))

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

################################################################################
#
# VcView
#
################################################################################
class VcView(melddoc.MeldDoc, gnomeglade.Component):
    # Map action names to VC commands and required arguments list
    action_vc_cmds_map = {
                         "VcCompare": ("diff_command", ()),
                         "VcCommit": ("commit_command", ("",)),
                         "VcUpdate": ("update_command", ()),
                         "VcAdd": ("add_command", ()),
                         "VcResolved": ("resolved_command", ()),
                         "VcRemove": ("remove_command", ()),
                         "VcRevert": ("revert_command", ()),
                         }

    state_actions = {
        "flatten": ("VcFlatten", None),
        "modified": ("VcShowModified", entry_modified),
        "normal": ("VcShowNormal", entry_normal),
        "unknown": ("VcShowNonVC", entry_nonvc),
        "ignored": ("VcShowIgnored", entry_ignored),
    }

    def __init__(self, prefs):
        melddoc.MeldDoc.__init__(self, prefs)
        gnomeglade.Component.__init__(self, paths.ui_dir("vcview.ui"), "vcview")

        actions = (
            ("VcCompare",       gtk.STOCK_DIALOG_INFO,      _("_Compare"),      None, _("Compare selected"), self.on_button_diff_clicked),
            ("VcCommit",        "vc-commit-24",             _("Co_mmit"),       None, _("Commit"), self.on_button_commit_clicked),
            ("VcUpdate",        "vc-update-24",             _("_Update"),       None, _("Update"), self.on_button_update_clicked),
            ("VcAdd",           "vc-add-24",                _("_Add"),          None, _("Add to VC"), self.on_button_add_clicked),
            ("VcRemove",        "vc-remove-24",             _("_Remove"),       None, _("Remove from VC"), self.on_button_remove_clicked),
            ("VcResolved",      "vc-resolve-24",            _("_Resolved"),     None, _("Mark as resolved for VC"), self.on_button_resolved_clicked),
            ("VcRevert",        gtk.STOCK_REVERT_TO_SAVED,  None,               None, _("Revert to original"), self.on_button_revert_clicked),
            ("VcDeleteLocally", gtk.STOCK_DELETE,           None,               None, _("Delete locally"), self.on_button_delete_clicked),
        )

        toggleactions = (
            ("VcFlatten",     gtk.STOCK_GOTO_BOTTOM, _("_Flatten"),  None, _("Flatten directories"), self.on_button_flatten_toggled, False),
            ("VcShowModified","filter-modified-24",  _("_Modified"), None, _("Show modified"), self.on_filter_state_toggled, False),
            ("VcShowNormal",  "filter-normal-24",    _("_Normal"),   None, _("Show normal"), self.on_filter_state_toggled, False),
            ("VcShowNonVC",   "filter-nonvc-24",     _("Non _VC"),   None, _("Show unversioned files"), self.on_filter_state_toggled, False),
            ("VcShowIgnored", "filter-ignored-24",   _("Ignored"),   None, _("Show ignored files"), self.on_filter_state_toggled, False),
        )

        self.ui_file = paths.ui_dir("vcview-ui.xml")
        self.actiongroup = gtk.ActionGroup('VcviewActions')
        self.actiongroup.set_translation_domain("meld")
        self.actiongroup.add_actions(actions)
        self.actiongroup.add_toggle_actions(toggleactions)
        for action in ("VcCompare", "VcFlatten", "VcShowModified",
                       "VcShowNormal", "VcShowNonVC", "VcShowIgnored"):
            self.actiongroup.get_action(action).props.is_important = True
        for action in ("VcCommit", "VcUpdate", "VcAdd", "VcRemove",
                       "VcShowModified", "VcShowNormal", "VcShowNonVC",
                       "VcShowIgnored", "VcResolved"):
            button = self.actiongroup.get_action(action)
            button.props.icon_name = button.props.stock_id
        self.model = VcTreeStore()
        self.widget.connect("style-set", self.model.on_style_set)
        self.treeview.set_model(self.model)
        selection = self.treeview.get_selection()
        selection.set_mode(gtk.SELECTION_MULTIPLE)
        selection.connect("changed", self.on_treeview_selection_changed)
        self.treeview.set_headers_visible(1)
        self.treeview.set_search_equal_func(self.treeview_search_cb)
        self.current_path, self.prev_path, self.next_path = None, None, None
        column = gtk.TreeViewColumn( _("Name") )
        renicon = emblemcellrenderer.EmblemCellRenderer()
        rentext = gtk.CellRendererText()
        column.pack_start(renicon, expand=0)
        column.pack_start(rentext, expand=1)
        col_index = self.model.column_index
        column.set_attributes(renicon,
                              icon_name=col_index(tree.COL_ICON, 0),
                              icon_tint=col_index(tree.COL_TINT, 0))
        column.set_attributes(rentext,
                    text=col_index(tree.COL_TEXT, 0),
                    foreground_gdk=col_index(tree.COL_FG, 0),
                    style=col_index(tree.COL_STYLE, 0),
                    weight=col_index(tree.COL_WEIGHT, 0),
                    strikethrough=col_index(tree.COL_STRIKE, 0))

        self.treeview.append_column(column)

        def addCol(name, num):
            column = gtk.TreeViewColumn(name)
            rentext = gtk.CellRendererText()
            column.pack_start(rentext, expand=0)
            column.set_attributes(rentext, markup=self.model.column_index(num, 0))
            self.treeview.append_column(column)
            return column

        self.treeview_column_location = addCol( _("Location"), COL_LOCATION)
        addCol(_("Status"), COL_STATUS)
        addCol(_("Rev"), COL_REVISION)
        addCol(_("Tag"), COL_TAG)
        addCol(_("Options"), COL_OPTIONS)


        self.state_filters = []
        for s in self.state_actions:
            if s in self.prefs.vc_status_filters:
                action_name = self.state_actions[s][0]
                self.state_filters.append(s)
                self.actiongroup.get_action(action_name).set_active(True)

        class ConsoleStream(object):
            def __init__(self, textview):
                self.textview = textview
                b = textview.get_buffer()
                self.mark = b.create_mark("END", b.get_end_iter(), 0)
            def write(self, s):
                if s:
                    b = self.textview.get_buffer()
                    b.insert(b.get_end_iter(), s)
                    self.textview.scroll_mark_onscreen( self.mark )
        self.consolestream = ConsoleStream(self.consoleview)
        self.location = None
        self.treeview_column_location.set_visible(self.actiongroup.get_action("VcFlatten").get_active())
        if not self.prefs.vc_console_visible:
            self.on_console_view_toggle(self.console_hide_box)
        self.vc = None
        self.valid_vc_actions = tuple()
        # VC ComboBox
        self.combobox_vcs = gtk.ComboBox()
        self.combobox_vcs.lock = True
        self.combobox_vcs.set_model(gtk.ListStore(str, object, bool))
        cell = gtk.CellRendererText()
        self.combobox_vcs.pack_start(cell, False)
        self.combobox_vcs.add_attribute(cell, 'text', 0)
        self.combobox_vcs.add_attribute(cell, 'sensitive', 2)
        self.combobox_vcs.lock = False
        self.hbox2.pack_end(self.combobox_vcs, expand=False)
        self.combobox_vcs.show()
        self.combobox_vcs.connect("changed", self.on_vc_change)

    def on_container_switch_in_event(self, ui):
        melddoc.MeldDoc.on_container_switch_in_event(self, ui)
        self.scheduler.add_task(self.on_treeview_cursor_changed)

    def update_actions_sensitivity(self):
        """Disable actions that use not implemented VC plugin methods
        """
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

    def choose_vc(self, vcs):
        """Display VC plugin(s) that can handle the location"""
        self.combobox_vcs.lock = True
        self.combobox_vcs.get_model().clear()
        tooltip_texts = [_("Choose one Version Control"),
                         _("Only one Version Control in this directory")]
        default_active = -1
        valid_vcs = []
        # Try to keep the same VC plugin active on refresh()
        for idx, avc in enumerate(vcs):
            # See if the necessary version control command exists.  If so,
            # make sure what we're diffing is a valid respository.  If either
            # check fails don't let the user select the that version control
            # tool and display a basic error message in the drop-down menu.
            err_str = ""
            if vc._vc.call(["which", avc.CMD]):
                # TRANSLATORS: this is an error message when a version control
                # application isn't installed or can't be found
                err_str = _("%s Not Installed" % avc.CMD)
            elif not avc.valid_repo():
                # TRANSLATORS: this is an error message when a version
                # controlled repository is invalid or corrupted
                err_str = _("Invalid Repository")
            else:
                valid_vcs.append(idx)
                if (self.vc is not None and
                     self.vc.__class__ == avc.__class__):
                     default_active = idx

            if err_str:
                self.combobox_vcs.get_model().append( \
                        [_("%s (%s)") % (avc.NAME, err_str), avc, False])
            else:
                self.combobox_vcs.get_model().append([avc.NAME, avc, True])

        if valid_vcs and default_active == -1:
            default_active = min(valid_vcs)

        self.combobox_vcs.set_tooltip_text(tooltip_texts[len(vcs) == 1])
        self.combobox_vcs.set_sensitive(len(vcs) > 1)
        self.combobox_vcs.lock = False
        self.combobox_vcs.set_active(default_active)
  
    def on_vc_change(self, cb):
        if not cb.lock:
            self.vc = cb.get_model()[cb.get_active_iter()][1]
            self._set_location(self.vc.location)
            self.update_actions_sensitivity()

    def set_location(self, location):
        self.choose_vc(vc.get_vcs(os.path.abspath(location or ".")))

    def _set_location(self, location):
        self.location = location
        self.current_path = None
        self.model.clear()
        self.fileentry.set_filename(location)
        self.fileentry.prepend_history(location)
        it = self.model.add_entries( None, [location] )
        self.treeview.grab_focus()
        self.treeview.get_selection().select_iter(it)
        self.model.set_path_state(it, 0, tree.STATE_NORMAL, isdir=1)
        self.recompute_label()
        self.scheduler.remove_all_tasks()

        # If the user is just diffing a file (ie not a directory), there's no
        # need to scan the rest of the repository
        if os.path.isdir(self.vc.location):
            root = self.model.get_iter_root()
            self.scheduler.add_task(self._search_recursively_iter(root))
            self.scheduler.add_task(self.on_treeview_cursor_changed)

    def get_comparison(self):
        return recent.TYPE_VC, [self.location]

    def recompute_label(self):
        self.label_text = os.path.basename(self.location)
        # TRANSLATORS: This is the location of the directory the user is diffing
        self.tooltip_text = _("%s: %s") % (_("Location"), self.location)
        self.label_changed()

    def _search_recursively_iter(self, iterstart):
        yield _("[%s] Scanning %s") % (self.label_text,"")
        rootpath = self.model.get_path( iterstart  )
        rootname = self.model.value_path( self.model.get_iter(rootpath), 0 )
        prefixlen = 1 + len( self.model.value_path( self.model.get_iter_root(), 0 ) )
        todo = [ (rootpath, rootname) ]

        active_action = lambda a: self.actiongroup.get_action(a).get_active()
        filters = [a[1] for a in self.state_actions.values() if \
                   active_action(a[0]) and a[1]]

        def showable(entry):
            for f in filters:
                if f(entry): return 1
        recursive = self.actiongroup.get_action("VcFlatten").get_active()
        self.vc.cache_inventory(rootname)
        while len(todo):
            todo.sort() # depth first
            path, name = todo.pop(0)
            if path:
                it = self.model.get_iter( path )
                root = self.model.value_path( it, 0 )
            else:
                it = self.model.get_iter_root()
                root = name
            yield _("[%s] Scanning %s") % (self.label_text, root[prefixlen:])

            entries = [f for f in self.vc.listdir(root) if showable(f)]
            differences = 0
            for e in entries:
                differences |= (e.state != tree.STATE_NORMAL)
                if e.isdir and recursive:
                    todo.append( (None, e.path) )
                    continue
                child = self.model.add_entries(it, [e.path])
                self._update_item_state( child, e, root[prefixlen:] )
                if e.isdir:
                    todo.append( (self.model.get_path(child), None) )
            if not recursive: # expand parents
                if len(entries) == 0:
                    self.model.add_empty(it, _("(Empty)"))
                if differences or len(path)==1:
                    self.treeview.expand_to_path(path)
            else: # just the root
                self.treeview.expand_row( (0,), 0)
        self.vc.uncache_inventory()

    def on_fileentry_activate(self, fileentry):
        path = fileentry.get_full_path()
        self.set_location(path)

    def on_delete_event(self, appquit=0):
        self.scheduler.remove_all_tasks()
        return gtk.RESPONSE_OK

    def on_row_activated(self, treeview, path, tvc):
        it = self.model.get_iter(path)
        if self.model.iter_has_child(it):
            if self.treeview.row_expanded(path):
                self.treeview.collapse_row(path)
            else:
                self.treeview.expand_row(path,0)
        else:
            path = self.model.value_path(it, 0)
            self.run_diff( [path] )

    def run_diff_iter(self, path_list):
        silent_error = hasattr(self.vc, 'switch_to_external_diff')
        retry_diff = True
        while retry_diff:
            retry_diff = False

            yield _("[%s] Fetching differences") % self.label_text
            diffiter = self._command_iter(self.vc.diff_command(), path_list, 0)
            diff = None
            while type(diff) != type(()):
                diff = next(diffiter)
                yield 1
            prefix, patch = diff[0], diff[1]

            try:
                patch = self.vc.clean_patch(patch)
            except AttributeError:
                pass

            yield _("[%s] Applying patch") % self.label_text
            if patch:
                applied = self.show_patch(prefix, patch, silent=silent_error)
                if not applied and silent_error:
                    silent_error = False
                    self.vc.switch_to_external_diff()
                    retry_diff = True
            else:
                for path in path_list:
                    self.emit("create-diff", [path])

    def run_diff(self, path_list):
        try:
            for path in path_list:
                comp_path = self.vc.get_path_for_repo_file(path)
                os.chmod(comp_path, 0o444)
                _temp_files.append(comp_path)
                self.emit("create-diff", [comp_path, path])
        except NotImplementedError:
            for path in path_list:
                self.scheduler.add_task(self.run_diff_iter([path]), atfront=1)

    def on_treeview_popup_menu(self, treeview):
        time = gtk.get_current_event_time()
        self.popup_menu.popup(None, None, None, 0, time)
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

            self.popup_menu.popup(None, None, None, event.button, event.time)
            return True
        return False

    def on_button_flatten_toggled(self, button):
        action = self.actiongroup.get_action("VcFlatten")
        self.treeview_column_location.set_visible(action.get_active())
        self.on_filter_state_toggled(button)

    def on_filter_state_toggled(self, button):
        active_action = lambda a: self.actiongroup.get_action(a).get_active()
        active_filters = [a for a in self.state_actions if \
                          active_action(self.state_actions[a][0])]

        if set(active_filters) == set(self.state_filters):
            return

        self.state_filters = active_filters
        self.prefs.vc_status_filters = active_filters
        self.refresh()

    def on_treeview_selection_changed(self, selection):
        model, rows = selection.get_selected_rows()
        have_selection = bool(rows)
        for action in self.valid_vc_actions:
            self.actiongroup.get_action(action).set_sensitive(have_selection)

    def _get_selected_files(self):
        model, rows = self.treeview.get_selection().get_selected_rows()
        sel = [self.model.value_path(self.model.get_iter(r), 0) for r in rows]
        # Remove empty entries and trailing slashes
        return [x[-1] != "/" and x or x[:-1] for x in sel if x is not None]

    def _command_iter(self, command, files, refresh):
        """Run 'command' on 'files'. Return a tuple of the directory the
           command was executed in and the output of the command.
        """
        msg = misc.shelljoin(command)
        yield "[%s] %s" % (self.label_text, msg.replace("\n", "\t"))
        def relpath(pbase, p):
            kill = 0
            if len(pbase) and p.startswith(pbase):
                kill = len(pbase) + 1
            return p[kill:] or "."
        if len(files) == 1 and os.path.isdir(files[0]):
            workdir = self.vc.get_working_directory(files[0])
        else:
            workdir = self.vc.get_working_directory( _commonprefix(files) )
        files = [ relpath(workdir, f) for f in files ]
        r = None
        self.consolestream.write( misc.shelljoin(command+files) + " (in %s)\n" % workdir)
        readiter = misc.read_pipe_iter(command + files, self.consolestream,
                                       workdir=workdir)
        try:
            while r is None:
                r = next(readiter)
                self.consolestream.write(r)
                yield 1
        except IOError as e:
            misc.run_dialog("Error running command.\n'%s'\n\nThe error was:\n%s" % ( misc.shelljoin(command), e),
                parent=self, messagetype=gtk.MESSAGE_ERROR)
        if refresh:
            self.refresh_partial(workdir)
        yield workdir, r

    def _command(self, command, files, refresh=1):
        """Run 'command' on 'files'.
        """
        self.scheduler.add_task(self._command_iter(command, files, refresh))

    def _command_on_selected(self, command, refresh=1):
        files = self._get_selected_files()
        if len(files):
            self._command(command, files, refresh)

    def on_button_update_clicked(self, obj):
        self._command_on_selected(self.vc.update_command())

    def on_button_commit_clicked(self, obj):
        CommitDialog(self).run()

    def on_button_add_clicked(self, obj):
        self._command_on_selected(self.vc.add_command())

    def on_button_remove_clicked(self, obj):
        self._command_on_selected(self.vc.remove_command())

    def on_button_resolved_clicked(self, obj):
        self._command_on_selected(self.vc.resolved_command())

    def on_button_revert_clicked(self, obj):
        self._command_on_selected(self.vc.revert_command())

    def on_button_delete_clicked(self, obj):
        files = self._get_selected_files()
        for name in files:
            try:
                if os.path.isfile(name):
                    os.remove(name)
                elif os.path.isdir(name):
                    if misc.run_dialog(_("'%s' is a directory.\nRemove recursively?") % os.path.basename(name),
                            parent = self,
                            buttonstype=gtk.BUTTONS_OK_CANCEL) == gtk.RESPONSE_OK:
                        shutil.rmtree(name)
            except OSError as e:
                misc.run_dialog(_("Error removing %s\n\n%s.") % (name,e), parent = self)
        workdir = _commonprefix(files)
        self.refresh_partial(workdir)

    def on_button_diff_clicked(self, obj):
        files = self._get_selected_files()
        if len(files):
            self.run_diff(files)

    def open_external(self):
        self._open_files(self._get_selected_files())

    def show_patch(self, prefix, patch, silent=False):
        if vc._vc.call(["which", "patch"]):
            primary = _("Patch tool not found")
            secondary = _("Meld needs the <i>patch</i> tool to be installed "
                          "to perform comparisons in %s repositories. Please "
                          "install <i>patch</i> and try again.") % self.vc.NAME

            msgarea = self.msgarea_mgr.new_from_text_and_icon(
                        gtk.STOCK_DIALOG_ERROR, primary, secondary)
            msgarea.add_button(_("Hi_de"), gtk.RESPONSE_CLOSE)
            msgarea.connect("response", lambda *args: self.msgarea_mgr.clear())
            msgarea.show_all()
            return False

        tmpdir = tempfile.mkdtemp("-meld")
        _temp_dirs.append(tmpdir)

        diffs = []
        for fname in self.vc.get_patch_files(patch):
            destfile = os.path.join(tmpdir,fname)
            destdir = os.path.dirname( destfile )

            if not os.path.exists(destdir):
                os.makedirs(destdir)
            pathtofile = os.path.join(prefix, fname)
            try:
                shutil.copyfile( pathtofile, destfile)
            except IOError: # it is missing, create empty file
                open(destfile,"w").close()
            diffs.append( (destfile, pathtofile) )

        patchcmd = self.vc.patch_command(tmpdir)
        try:
            result = misc.write_pipe(patchcmd, patch, error=misc.NULL)
        except OSError:
            result = 1

        if result == 0:
            for d in diffs:
                os.chmod(d[0], 0o444)
                self.emit("create-diff", d)
            return True
        elif not silent:
            primary = _("Error fetching original comparison file")
            secondary = _("Meld couldn't obtain the original version of your "
                          "comparison file. If you are using the most recent "
                          "version of Meld, please report a bug, including as "
                          "many details as possible.")

            msgarea = self.msgarea_mgr.new_from_text_and_icon(
                        gtk.STOCK_DIALOG_ERROR, primary, secondary)
            msgarea.add_button(_("Hi_de"), gtk.RESPONSE_CLOSE)
            msgarea.add_button(_("Report a bug"), gtk.RESPONSE_OK)

            def patch_error_cb(msgarea, response):
                if response == gtk.RESPONSE_OK:
                    bug_url = "https://bugzilla.gnome.org/enter_bug.cgi?" + \
                              "product=meld"
                    misc.open_uri(bug_url)
                else:
                    self.msgarea_mgr.clear()

            msgarea.connect("response", patch_error_cb)
            msgarea.show_all()

        return False

    def refresh(self):
        self.set_location( self.model.value_path( self.model.get_iter_root(), 0 ) )

    def refresh_partial(self, where):
        if not self.actiongroup.get_action("VcFlatten").get_active():
            it = self.find_iter_by_name( where )
            if it:
                newiter = self.model.insert_after( None, it)
                self.model.set_value(newiter, self.model.column_index( tree.COL_PATH, 0), where)
                self.model.set_path_state(newiter, 0, tree.STATE_NORMAL, True)
                self.model.remove(it)
                self.scheduler.add_task(self._search_recursively_iter(newiter))
        else: # XXX fixme
            self.refresh()

    def _update_item_state(self, it, vcentry, location):
        e = vcentry
        self.model.set_path_state(it, 0, e.state, e.isdir)
        def setcol(col, val):
            self.model.set_value(it, self.model.column_index(col, 0), val)
        setcol(COL_LOCATION, location)
        setcol(COL_STATUS, e.get_status())
        setcol(COL_REVISION, e.rev)
        setcol(COL_TAG, e.tag)
        setcol(COL_OPTIONS, e.options)

    def on_file_changed(self, filename):
        it = self.find_iter_by_name(filename)
        if it:
            path = self.model.value_path(it, 0)
            self.vc.update_file_state(path)
            files = self.vc.lookup_files([], [(os.path.basename(path), path)])[1]
            for e in files:
                if e.path == path:
                    prefixlen = 1 + len( self.model.value_path( self.model.get_iter_root(), 0 ) )
                    self._update_item_state( it, e, e.parent[prefixlen:])
                    return

    def find_iter_by_name(self, name):
        it = self.model.get_iter_root()
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

    def on_console_view_toggle(self, box, event=None):
        if box == self.console_hide_box:
            self.prefs.vc_console_visible = 0
            self.console_hbox.hide()
            self.console_show_box.show()
        else:
            self.prefs.vc_console_visible = 1
            self.console_hbox.show()
            self.console_show_box.hide()

    def on_consoleview_populate_popup(self, text, menu):
        item = gtk.ImageMenuItem(gtk.STOCK_CLEAR)
        def activate(*args):
            buf = text.get_buffer()
            buf.delete( buf.get_start_iter(), buf.get_end_iter() )
        item.connect("activate", activate)
        item.show()
        menu.insert( item, 0 )
        item = gtk.SeparatorMenuItem()
        item.show()
        menu.insert( item, 1 )

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
        if direction == gtk.gdk.SCROLL_UP:
            path = self.prev_path
        else:
            path = self.next_path
        if path:
            self.treeview.expand_to_path(path)
            self.treeview.set_cursor(path)

    def on_reload_activate(self, *extra):
        self.on_fileentry_activate(self.fileentry)

    def on_find_activate(self, *extra):
        self.treeview.emit("start-interactive-search")

    def treeview_search_cb(self, model, column, key, it):
        """Callback function for searching in VcView treeview"""
        path = model.get_value(it, tree.COL_PATH)

        # if query text contains slash, search in full path
        if key.find('/') >= 0:
            lineText = path
        else:
            lineText = os.path.basename(path)

        # Perform case-insensitive matching if query text is all lower-case
        if key.islower():
            lineText = lineText.lower()

        if lineText.find(key) >= 0:
            # line matches
            return False
        else:
            return True
