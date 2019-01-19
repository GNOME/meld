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

import os

from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import Gtk

import meld.ui.util
from meld.conf import _
from meld.dirdiff import DirDiff
from meld.filediff import FileDiff
from meld.filemerge import FileMerge
from meld.melddoc import ComparisonState, MeldDoc
from meld.newdifftab import NewDiffTab
from meld.recent import recent_comparisons, RecentType
from meld.settings import interface_settings, settings
from meld.task import LifoScheduler
from meld.ui.gnomeglade import Component, ui_file
from meld.ui.notebooklabel import NotebookLabel
from meld.vcview import VcView
from meld.windowstate import SavedWindowState


class MeldWindow(Component):

    def __init__(self):
        super().__init__("meldapp.ui", "meldapp")
        self.widget.set_name("meldapp")

        actions = (
            ("FileMenu", None, _("_File")),
            ("New", Gtk.STOCK_NEW, _("_New Comparison…"), "<Primary>N",
                _("Start a new comparison"),
                self.on_menu_file_new_activate),
            ("Save", Gtk.STOCK_SAVE, None, None,
                _("Save the current file"),
                self.on_menu_save_activate),
            ("SaveAs", Gtk.STOCK_SAVE_AS, _("Save As…"), "<Primary><shift>S",
                _("Save the current file with a different name"),
                self.on_menu_save_as_activate),
            ("Close", Gtk.STOCK_CLOSE, None, None,
                _("Close the current file"),
                self.on_menu_close_activate),

            ("EditMenu", None, _("_Edit")),
            ("Undo", Gtk.STOCK_UNDO, None, "<Primary>Z",
                _("Undo the last action"),
                self.on_menu_undo_activate),
            ("Redo", Gtk.STOCK_REDO, None, "<Primary><shift>Z",
                _("Redo the last undone action"),
                self.on_menu_redo_activate),
            ("Cut", Gtk.STOCK_CUT, None, None, _("Cut the selection"),
                self.on_menu_cut_activate),
            ("Copy", Gtk.STOCK_COPY, None, None, _("Copy the selection"),
                self.on_menu_copy_activate),
            ("Paste", Gtk.STOCK_PASTE, None, None, _("Paste the clipboard"),
                self.on_menu_paste_activate),
            ("Find", Gtk.STOCK_FIND, _("Find…"), None, _("Search for text"),
                self.on_menu_find_activate),
            ("FindNext", None, _("Find Ne_xt"), "<Primary>G",
                _("Search forwards for the same text"),
                self.on_menu_find_next_activate),
            ("FindPrevious", None, _("Find _Previous"), "<Primary><shift>G",
                _("Search backwards for the same text"),
                self.on_menu_find_previous_activate),
            ("Replace", Gtk.STOCK_FIND_AND_REPLACE,
                _("_Replace…"), "<Primary>H",
                _("Find and replace text"),
                self.on_menu_replace_activate),
            ("GoToLine", None, _("Go to _Line"), "<Primary>I",
                _("Go to a specific line"),
                self.on_menu_go_to_line_activate),

            ("ChangesMenu", None, _("_Changes")),
            ("NextChange", Gtk.STOCK_GO_DOWN, _("Next Change"), "<Alt>Down",
                _("Go to the next change"),
                self.on_menu_edit_down_activate),
            ("PrevChange", Gtk.STOCK_GO_UP, _("Previous Change"), "<Alt>Up",
                _("Go to the previous change"),
                self.on_menu_edit_up_activate),
            ("OpenExternal", None, _("Open Externally"), None,
                _("Open selected file or directory in the default external "
                  "application"),
                self.on_open_external),

            ("ViewMenu", None, _("_View")),
            ("FileStatus", None, _("File Status")),
            ("VcStatus", None, _("Version Status")),
            ("FileFilters", None, _("File Filters")),
            ("Stop", Gtk.STOCK_STOP, None, "Escape",
                _("Stop the current action"),
                self.on_toolbar_stop_clicked),
            ("Refresh", Gtk.STOCK_REFRESH, None, "<Primary>R",
                _("Refresh the view"),
                self.on_menu_refresh_activate),
        )
        toggleactions = (
            ("Fullscreen", None, _("Fullscreen"), "F11",
                _("View the comparison in fullscreen"),
                self.on_action_fullscreen_toggled, False),
            ("ToolbarVisible", None, _("_Toolbar"), None,
                _("Show or hide the toolbar"),
                None, True),
        )
        self.actiongroup = Gtk.ActionGroup(name='MainActions')
        self.actiongroup.set_translation_domain("meld")
        self.actiongroup.add_actions(actions)
        self.actiongroup.add_toggle_actions(toggleactions)

        recent_action = Gtk.RecentAction(
            name="Recent",  label=_("Open Recent"),
            tooltip=_("Open recent files"), stock_id=None)
        recent_action.set_show_private(True)
        recent_action.set_filter(recent_comparisons.recent_filter)
        recent_action.set_sort_type(Gtk.RecentSortType.MRU)
        recent_action.connect("item-activated", self.on_action_recent)
        self.actiongroup.add_action(recent_action)

        self.ui = Gtk.UIManager()
        self.ui.insert_action_group(self.actiongroup, 0)
        self.ui.add_ui_from_file(ui_file("meldapp-ui.xml"))

        # Manually handle shells that don't show an application menu
        gtk_settings = Gtk.Settings.get_default()
        if not gtk_settings.props.gtk_shell_shows_app_menu:
            from meld.meldapp import app

            def make_app_action(name):
                def app_action(*args):
                    app.lookup_action(name).activate(None)
                return app_action

            app_actions = (
                ("AppMenu", None, _("_Meld")),
                ("Quit", Gtk.STOCK_QUIT, None, None, _("Quit the program"),
                 make_app_action('quit')),
                ("Preferences", Gtk.STOCK_PREFERENCES, _("Prefere_nces"), None,
                 _("Configure the application"),
                 make_app_action('preferences')),
                ("Help", Gtk.STOCK_HELP, _("_Contents"), "F1",
                 _("Open the Meld manual"), make_app_action('help')),
                ("About", Gtk.STOCK_ABOUT, None, None,
                 _("About this application"), make_app_action('about')),
            )

            app_actiongroup = Gtk.ActionGroup(name="AppActions")
            app_actiongroup.set_translation_domain("meld")
            app_actiongroup.add_actions(app_actions)
            self.ui.insert_action_group(app_actiongroup, 0)

            self.ui.add_ui_from_file(ui_file("appmenu-fallback.xml"))
            self.widget.set_show_menubar(False)

        for menuitem in ("Save", "Undo"):
            self.actiongroup.get_action(menuitem).props.is_important = True
        self.widget.add_accel_group(self.ui.get_accel_group())
        self.menubar = self.ui.get_widget('/Menubar')
        self.toolbar = self.ui.get_widget('/Toolbar')
        self.toolbar.get_style_context().add_class(
            Gtk.STYLE_CLASS_PRIMARY_TOOLBAR)

        settings.bind('toolbar-visible',
                      self.actiongroup.get_action('ToolbarVisible'), 'active',
                      Gio.SettingsBindFlags.DEFAULT)
        settings.bind('toolbar-visible', self.toolbar, 'visible',
                      Gio.SettingsBindFlags.DEFAULT)
        interface_settings.bind('toolbar-style', self.toolbar, 'toolbar-style',
                                Gio.SettingsBindFlags.DEFAULT)

        # Alternate keybindings for a few commands.
        extra_accels = (
            ("<Primary>D", self.on_menu_edit_down_activate),
            ("<Primary>E", self.on_menu_edit_up_activate),
            ("<Alt>KP_Down", self.on_menu_edit_down_activate),
            ("<Alt>KP_Up", self.on_menu_edit_up_activate),
            ("F5", self.on_menu_refresh_activate),
        )

        accel_group = self.ui.get_accel_group()
        for accel, callback in extra_accels:
            keyval, mask = Gtk.accelerator_parse(accel)
            accel_group.connect(keyval, mask, 0, callback)

        # Initialise sensitivity for important actions
        self.actiongroup.get_action("Stop").set_sensitive(False)
        self._update_page_action_sensitivity()

        self.appvbox.pack_start(self.menubar, False, True, 0)
        self.toolbar_holder.pack_start(self.toolbar, True, True, 0)

        # Double toolbars to work around UIManager integration issues
        self.secondary_toolbar = Gtk.Toolbar()
        self.secondary_toolbar.get_style_context().add_class(
            Gtk.STYLE_CLASS_PRIMARY_TOOLBAR)
        self.toolbar_holder.pack_end(self.secondary_toolbar, False, True, 0)

        # Manually handle GAction additions
        actions = (
            ("close", self.on_menu_close_activate, None),
        )
        for (name, callback, accel) in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', callback)
            self.widget.add_action(action)

        # Create a secondary toolbar, just to hold our progress spinner
        toolbutton = Gtk.ToolItem()
        self.spinner = Gtk.Spinner()
        # Fake out the spinner on Windows. See Gitlab issue #133.
        if os.name == 'nt':
            for attr in ('stop', 'hide', 'show', 'start'):
                setattr(self.spinner, attr, lambda *args: True)
        toolbutton.add(self.spinner)
        self.secondary_toolbar.insert(toolbutton, -1)
        # Set a minimum size because the spinner requests nothing
        self.secondary_toolbar.set_size_request(30, -1)
        self.secondary_toolbar.show_all()

        self.widget.drag_dest_set(
            Gtk.DestDefaults.MOTION | Gtk.DestDefaults.HIGHLIGHT |
            Gtk.DestDefaults.DROP,
            None, Gdk.DragAction.COPY)
        self.widget.drag_dest_add_uri_targets()
        self.widget.connect("drag_data_received",
                            self.on_widget_drag_data_received)

        self.window_state = SavedWindowState()
        self.window_state.bind(self.widget)

        self.should_close = False
        self.idle_hooked = 0
        self.scheduler = LifoScheduler()
        self.scheduler.connect("runnable", self.on_scheduler_runnable)

        self.ui.ensure_update()
        self.diff_handler = None
        self.undo_handlers = tuple()
        self.widget.connect('focus_in_event', self.on_focus_change)
        self.widget.connect('focus_out_event', self.on_focus_change)

        # Set tooltip on map because the recentmenu is lazily created
        rmenu = self.ui.get_widget('/Menubar/FileMenu/Recent').get_submenu()
        rmenu.connect("map", self._on_recentmenu_map)

        builder = meld.ui.util.get_builder("shortcuts.ui")
        shortcut_window = builder.get_object("shortcuts-meld")
        self.widget.set_help_overlay(shortcut_window)

    def _on_recentmenu_map(self, recentmenu):
        for imagemenuitem in recentmenu.get_children():
            imagemenuitem.set_tooltip_text(imagemenuitem.get_label())

    def on_focus_change(self, widget, event, callback_data=None):
        for idx in range(self.notebook.get_n_pages()):
            w = self.notebook.get_nth_page(idx)
            if hasattr(w.pyobject, 'on_focus_change'):
                w.pyobject.on_focus_change()
        # Let the rest of the stack know about this event
        return False

    def on_widget_drag_data_received(
            self, wid, context, x, y, selection_data, info, time):
        uris = selection_data.get_uris()
        if uris:
            self.open_paths([Gio.File.new_for_uri(uri) for uri in uris])
            return True

    def on_idle(self):
        ret = self.scheduler.iteration()
        if ret and isinstance(ret, str):
            self.spinner.set_tooltip_text(ret)

        pending = self.scheduler.tasks_pending()
        if not pending:
            self.spinner.stop()
            self.spinner.hide()
            self.spinner.set_tooltip_text("")
            self.idle_hooked = None
            self.actiongroup.get_action("Stop").set_sensitive(False)
        return pending

    def on_scheduler_runnable(self, sched):
        if not self.idle_hooked:
            self.spinner.show()
            self.spinner.start()
            self.actiongroup.get_action("Stop").set_sensitive(True)
            self.idle_hooked = GLib.idle_add(self.on_idle)

    def on_delete_event(self, *extra):
        should_cancel = False
        # Delete pages from right-to-left.  This ensures that if a version
        # control page is open in the far left page, it will be closed last.
        for c in reversed(self.notebook.get_children()):
            page = c.pyobject
            self.notebook.set_current_page(self.notebook.page_num(page.widget))
            response = page.on_delete_event()
            if response == Gtk.ResponseType.CANCEL:
                should_cancel = True

        should_cancel = should_cancel or self.has_pages()
        if should_cancel:
            self.should_close = True
        return should_cancel

    def has_pages(self):
        return self.notebook.get_n_pages() > 0

    def _update_page_action_sensitivity(self):
        current_page = self.notebook.get_current_page()

        if current_page != -1:
            page = self.notebook.get_nth_page(current_page).pyobject
        else:
            page = None

        self.actiongroup.get_action("Close").set_sensitive(bool(page))
        if not isinstance(page, MeldDoc):
            for action in ("PrevChange", "NextChange", "Cut", "Copy", "Paste",
                           "Find", "FindNext", "FindPrevious", "Replace",
                           "Refresh", "GoToLine"):
                self.actiongroup.get_action(action).set_sensitive(False)
        else:
            for action in ("Find", "Refresh"):
                self.actiongroup.get_action(action).set_sensitive(True)
            is_filediff = isinstance(page, FileDiff)
            for action in ("Cut", "Copy", "Paste", "FindNext", "FindPrevious",
                           "Replace", "GoToLine"):
                self.actiongroup.get_action(action).set_sensitive(is_filediff)

    def handle_current_doc_switch(self, page):
        if self.diff_handler is not None:
            page.disconnect(self.diff_handler)
        page.on_container_switch_out_event(self.ui)
        if self.undo_handlers:
            undoseq = page.undosequence
            for handler in self.undo_handlers:
                undoseq.disconnect(handler)
            self.undo_handlers = tuple()

    def on_switch_page(self, notebook, page, which):
        oldidx = notebook.get_current_page()
        if oldidx >= 0:
            olddoc = notebook.get_nth_page(oldidx).pyobject
            self.handle_current_doc_switch(olddoc)

        newdoc = notebook.get_nth_page(which).pyobject if which >= 0 else None
        try:
            undoseq = newdoc.undosequence
            can_undo = undoseq.can_undo()
            can_redo = undoseq.can_redo()
            undo_handler = undoseq.connect("can-undo", self.on_can_undo)
            redo_handler = undoseq.connect("can-redo", self.on_can_redo)
            self.undo_handlers = (undo_handler, redo_handler)
        except AttributeError:
            can_undo, can_redo = False, False
        self.actiongroup.get_action("Undo").set_sensitive(can_undo)
        self.actiongroup.get_action("Redo").set_sensitive(can_redo)

        # FileDiff handles save sensitivity; it makes no sense for other modes
        if not isinstance(newdoc, FileDiff):
            self.actiongroup.get_action("Save").set_sensitive(False)
            self.actiongroup.get_action("SaveAs").set_sensitive(False)
        else:
            self.actiongroup.get_action("SaveAs").set_sensitive(True)

        if newdoc:
            nbl = self.notebook.get_tab_label(newdoc.widget)
            self.widget.set_title(nbl.get_label_text())
            newdoc.on_container_switch_in_event(self.ui)
        else:
            self.widget.set_title("Meld")

        if isinstance(newdoc, MeldDoc):
            self.diff_handler = newdoc.connect("next-diff-changed",
                                               self.on_next_diff_changed)
        else:
            self.diff_handler = None
        if hasattr(newdoc, 'scheduler'):
            self.scheduler.add_task(newdoc.scheduler)

    def after_switch_page(self, notebook, page, which):
        self._update_page_action_sensitivity()

    def after_page_reordered(self, notebook, page, page_num):
        self._update_page_action_sensitivity()

    def on_page_label_changed(self, notebook, label_text):
        self.widget.set_title(label_text)

    def on_can_undo(self, undosequence, can):
        self.actiongroup.get_action("Undo").set_sensitive(can)

    def on_can_redo(self, undosequence, can):
        self.actiongroup.get_action("Redo").set_sensitive(can)

    def on_next_diff_changed(self, doc, have_prev, have_next):
        self.actiongroup.get_action("PrevChange").set_sensitive(have_prev)
        self.actiongroup.get_action("NextChange").set_sensitive(have_next)

    def on_menu_file_new_activate(self, menuitem):
        self.append_new_comparison()

    def on_menu_save_activate(self, menuitem):
        self.current_doc().save()

    def on_menu_save_as_activate(self, menuitem):
        self.current_doc().save_as()

    def on_action_recent(self, action):
        uri = action.get_current_uri()
        if not uri:
            return
        try:
            self.append_recent(uri)
        except (IOError, ValueError):
            # FIXME: Need error handling, but no sensible display location
            pass

    def on_menu_close_activate(self, *extra):
        i = self.notebook.get_current_page()
        if i >= 0:
            page = self.notebook.get_nth_page(i).pyobject
            page.on_delete_event()

    def on_menu_undo_activate(self, *extra):
        self.current_doc().on_undo_activate()

    def on_menu_redo_activate(self, *extra):
        self.current_doc().on_redo_activate()

    def on_menu_refresh_activate(self, *extra):
        self.current_doc().on_refresh_activate()

    def on_menu_find_activate(self, *extra):
        self.current_doc().on_find_activate()

    def on_menu_find_next_activate(self, *extra):
        self.current_doc().on_find_next_activate()

    def on_menu_find_previous_activate(self, *extra):
        self.current_doc().on_find_previous_activate()

    def on_menu_replace_activate(self, *extra):
        self.current_doc().on_replace_activate()

    def on_menu_go_to_line_activate(self, *extra):
        self.current_doc().on_go_to_line_activate()

    def on_menu_copy_activate(self, *extra):
        widget = self.widget.get_focus()
        if isinstance(widget, Gtk.Editable):
            widget.copy_clipboard()
        elif isinstance(widget, Gtk.TextView):
            widget.emit("copy-clipboard")

    def on_menu_cut_activate(self, *extra):
        widget = self.widget.get_focus()
        if isinstance(widget, Gtk.Editable):
            widget.cut_clipboard()
        elif isinstance(widget, Gtk.TextView):
            widget.emit("cut-clipboard")

    def on_menu_paste_activate(self, *extra):
        widget = self.widget.get_focus()
        if isinstance(widget, Gtk.Editable):
            widget.paste_clipboard()
        elif isinstance(widget, Gtk.TextView):
            widget.emit("paste-clipboard")

    def on_action_fullscreen_toggled(self, widget):
        window_state = self.widget.get_window().get_state()
        is_full = window_state & Gdk.WindowState.FULLSCREEN
        if widget.get_active() and not is_full:
            self.widget.fullscreen()
        elif is_full:
            self.widget.unfullscreen()

    def on_menu_edit_down_activate(self, *args):
        self.current_doc().next_diff(Gdk.ScrollDirection.DOWN)

    def on_menu_edit_up_activate(self, *args):
        self.current_doc().next_diff(Gdk.ScrollDirection.UP)

    def on_open_external(self, *args):
        self.current_doc().open_external()

    def on_toolbar_stop_clicked(self, *args):
        self.current_doc().stop()

    def page_removed(self, page, status):
        if hasattr(page, 'scheduler'):
            self.scheduler.remove_scheduler(page.scheduler)

        page_num = self.notebook.page_num(page.widget)

        if self.notebook.get_current_page() == page_num:
            self.handle_current_doc_switch(page)

        self.notebook.remove_page(page_num)
        # Normal switch-page handlers don't get run for removing the
        # last page from a notebook.
        if not self.has_pages():
            self.on_switch_page(self.notebook, page, -1)
            self._update_page_action_sensitivity()
            # Synchronise UIManager state; this shouldn't be necessary,
            # but upstream aren't touching UIManager bugs.
            self.ui.ensure_update()
            if self.should_close:
                cancelled = self.widget.emit(
                    'delete-event', Gdk.Event.new(Gdk.EventType.DELETE))
                if not cancelled:
                    self.widget.emit('destroy')

    def on_page_state_changed(self, page, old_state, new_state):
        if self.should_close and old_state == ComparisonState.Closing:
            # Cancel closing if one of our tabs does
            self.should_close = False

    def on_file_changed(self, srcpage, filename):
        for c in self.notebook.get_children():
            page = c.pyobject
            if page != srcpage:
                page.on_file_changed(filename)

    def _append_page(self, page, icon):
        nbl = NotebookLabel(icon, "", lambda b: page.on_delete_event())
        self.notebook.append_page(page.widget, nbl)

        # Change focus to the newly created page only if the user is on a
        # DirDiff or VcView page, or if it's a new tab page. This prevents
        # cycling through X pages when X diffs are initiated.
        if isinstance(self.current_doc(), DirDiff) or \
           isinstance(self.current_doc(), VcView) or \
           isinstance(page, NewDiffTab):
            self.notebook.set_current_page(self.notebook.page_num(page.widget))

        if hasattr(page, 'scheduler'):
            self.scheduler.add_scheduler(page.scheduler)
        if isinstance(page, MeldDoc):
            page.connect("file-changed", self.on_file_changed)
            page.connect("create-diff", lambda obj, arg, kwargs:
                         self.append_diff(arg, **kwargs))
            page.connect("state-changed", self.on_page_state_changed)
        page.connect("close", self.page_removed)

        self.notebook.set_tab_reorderable(page.widget, True)

    def append_new_comparison(self):
        doc = NewDiffTab(self)
        self._append_page(doc, "document-new")
        self.notebook.on_label_changed(doc, _("New comparison"), None)

        def diff_created_cb(doc, newdoc):
            doc.on_delete_event()
            idx = self.notebook.page_num(newdoc.widget)
            self.notebook.set_current_page(idx)

        doc.connect("diff-created", diff_created_cb)
        return doc

    def append_dirdiff(self, gfiles, auto_compare=False):
        dirs = [d.get_path() if d else None for d in gfiles]
        assert len(dirs) in (1, 2, 3)
        doc = DirDiff(len(dirs))
        self._append_page(doc, "folder")
        doc.set_locations(dirs)
        if auto_compare:
            doc.scheduler.add_task(doc.auto_compare)
        return doc

    def append_filediff(
            self, gfiles, *, encodings=None, merge_output=None, meta=None):
        assert len(gfiles) in (1, 2, 3)
        doc = FileDiff(len(gfiles))
        self._append_page(doc, "text-x-generic")
        doc.set_files(gfiles, encodings)
        if merge_output is not None:
            doc.set_merge_output_file(merge_output)
        if meta is not None:
            doc.set_meta(meta)
        return doc

    def append_filemerge(self, gfiles, merge_output=None):
        if len(gfiles) != 3:
            raise ValueError(
                _("Need three files to auto-merge, got: %r") %
                [f.get_parse_name() for f in gfiles])
        doc = FileMerge(len(gfiles))
        self._append_page(doc, "text-x-generic")
        doc.set_files(gfiles)
        if merge_output is not None:
            doc.set_merge_output_file(merge_output)
        return doc

    def append_diff(self, gfiles, auto_compare=False, auto_merge=False,
                    merge_output=None, meta=None):
        have_directories = False
        have_files = False
        for f in gfiles:
            if f.query_file_type(
               Gio.FileQueryInfoFlags.NONE, None) == Gio.FileType.DIRECTORY:
                have_directories = True
            else:
                have_files = True
        if have_directories and have_files:
            raise ValueError(
                _("Cannot compare a mixture of files and directories"))
        elif have_directories:
            return self.append_dirdiff(gfiles, auto_compare)
        elif auto_merge:
            return self.append_filemerge(gfiles, merge_output=merge_output)
        else:
            return self.append_filediff(
                gfiles, merge_output=merge_output, meta=meta)

    def append_vcview(self, location, auto_compare=False):
        doc = VcView()
        self._append_page(doc, "meld-version-control")
        if isinstance(location, (list, tuple)):
            location = location[0]
        doc.set_location(location.get_path())
        if auto_compare:
            doc.scheduler.add_task(doc.auto_compare)
        return doc

    def append_recent(self, uri):
        comparison_type, gfiles, flags = recent_comparisons.read(uri)
        comparison_method = {
            RecentType.File: self.append_filediff,
            RecentType.Folder: self.append_dirdiff,
            RecentType.Merge: self.append_filemerge,
            RecentType.VersionControl: self.append_vcview,
        }
        tab = comparison_method[comparison_type](gfiles)
        self.notebook.set_current_page(self.notebook.page_num(tab.widget))
        recent_comparisons.add(tab)
        return tab

    def _single_file_open(self, gfile):
        doc = VcView()

        def cleanup():
            self.scheduler.remove_scheduler(doc.scheduler)
        self.scheduler.add_task(cleanup)
        self.scheduler.add_scheduler(doc.scheduler)
        path = gfile.get_path()
        doc.set_location(path)
        doc.connect("create-diff", lambda obj, arg, kwargs:
                    self.append_diff(arg, **kwargs))
        doc.run_diff(path)

    def open_paths(self, gfiles, auto_compare=False, auto_merge=False,
                   focus=False):
        tab = None
        if len(gfiles) == 1:
            a = gfiles[0]
            if a.query_file_type(Gio.FileQueryInfoFlags.NONE, None) == \
                    Gio.FileType.DIRECTORY:
                tab = self.append_vcview(a, auto_compare)
            else:
                self._single_file_open(a)

        elif len(gfiles) in (2, 3):
            tab = self.append_diff(gfiles, auto_compare=auto_compare,
                                   auto_merge=auto_merge)
        if tab:
            recent_comparisons.add(tab)
            if focus:
                self.notebook.set_current_page(
                    self.notebook.page_num(tab.widget))

        return tab

    def current_doc(self):
        "Get the current doc or a dummy object if there is no current"
        index = self.notebook.get_current_page()
        if index >= 0:
            page = self.notebook.get_nth_page(index).pyobject
            if isinstance(page, MeldDoc):
                return page

        class DummyDoc:
            def __getattr__(self, a):
                return lambda *x: None
        return DummyDoc()
