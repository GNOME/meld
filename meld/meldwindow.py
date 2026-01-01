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

import logging
import os
from typing import Any, Dict, Optional, Sequence

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk

# Import support module to get all builder-constructed widgets in the namespace
import meld.ui.gladesupport  # noqa: F401
from meld.conf import PROFILE, _
from meld.const import (
    FILE_FILTER_ACTION_FORMAT,
    TEXT_FILTER_ACTION_FORMAT,
    FileComparisonMode,
    RecentType,
)
from meld.dirdiff import DirDiff
from meld.filediff import FileDiff
from meld.imagediff import ImageDiff, files_are_images
from meld.melddoc import ComparisonState, MeldDoc
from meld.menuhelpers import replace_menu_section
from meld.misc import guess_if_remote_x11
from meld.newdifftab import NewDiffTab
from meld.recent import get_recent_comparisons
from meld.settings import get_meld_settings
from meld.task import LifoScheduler
from meld.ui.gtkutil import BIND_DEFAULT_CREATE
from meld.vcview import VcView
from meld.windowstate import SavedWindowState

log = logging.getLogger(__name__)


@Gtk.Template(resource_path='/org/gnome/meld/ui/appwindow.ui')
class MeldWindow(Gtk.ApplicationWindow):

    __gtype_name__ = 'MeldWindow'

    appvbox = Gtk.Template.Child()
    folder_filter_button: Gtk.Button = Gtk.Template.Child()
    gear_menu_button = Gtk.Template.Child()
    next_conflict_button = Gtk.Template.Child()
    tabview = Gtk.Template.Child()
    previous_conflict_button = Gtk.Template.Child()
    spinner = Gtk.Template.Child()
    text_filter_button: Gtk.Button = Gtk.Template.Child()
    vc_filter_button: Gtk.Button = Gtk.Template.Child()
    view_toolbar = Gtk.Template.Child()

    def __init__(self):
        super().__init__()

        # Manually handle GAction additions
        actions = (
            ("close", self.action_close),
            ("new-tab", self.action_new_tab),
            ("stop", self.action_stop),
        )
        for name, callback in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', callback)
            self.add_action(action)

        state_actions = (
            (
                "fullscreen", self.action_fullscreen_change,
                GLib.Variant.new_boolean(False),
            ),
            (
                "gear-menu", None, GLib.Variant.new_boolean(False),
            ),
        )
        for (name, callback, state) in state_actions:
            action = Gio.SimpleAction.new_stateful(name, None, state)
            if callback:
                action.connect('change-state', callback)
            self.add_action(action)

        # Initialise sensitivity for important actions
        self.lookup_action('stop').set_enabled(False)

        # Fake out the spinner on Windows or X11 forwarding. See Gitlab
        # issues #133 and #507.
        if os.name == "nt" or guess_if_remote_x11():
            for attr in ('stop', 'hide', 'show', 'start'):
                setattr(self.spinner, attr, lambda *args: True)

        drop_target = Gtk.DropTarget.new(GObject.TYPE_NONE, Gdk.DragAction.COPY)
        drop_target.set_gtypes([Gdk.FileList])
        drop_target.connect("drop", self.on_widget_drag_drop)
        self.add_controller(drop_target)

        self.window_state = SavedWindowState()
        self.window_state.bind(self)

        self.should_close = False
        self.idle_hooked = 0
        self.scheduler = LifoScheduler()
        self.scheduler.connect("runnable", self.on_scheduler_runnable)

        if PROFILE != '':
            style_context = self.get_style_context()
            style_context.add_class("devel")

    def do_realize(self):
        Gtk.ApplicationWindow.do_realize(self)

        meld_settings = get_meld_settings()
        self.update_text_filters(meld_settings)
        self.update_filename_filters(meld_settings)
        self.settings_handlers = [
            meld_settings.connect(
                "text-filters-changed", self.update_text_filters),
            meld_settings.connect(
                "file-filters-changed", self.update_filename_filters),
        ]

    def update_filename_filters(self, settings):
        filter_items_model = Gio.Menu()
        for i, filt in enumerate(settings.file_filters):
            name = FILE_FILTER_ACTION_FORMAT.format(i)
            filter_items_model.append(
                label=filt.label, detailed_action=f'view.{name}')
        section = Gio.MenuItem.new_section(_("Filename"), filter_items_model)
        section.set_attribute([("id", "s", "custom-filter-section")])
        filter_model = self.folder_filter_button.get_menu_model()
        replace_menu_section(filter_model, section)

    def update_text_filters(self, settings):
        filter_items_model = Gio.Menu()
        for i, filt in enumerate(settings.text_filters):
            name = TEXT_FILTER_ACTION_FORMAT.format(i)
            filter_items_model.append(
                label=filt.label, detailed_action=f'view.{name}')
        section = Gio.MenuItem.new_section(None, filter_items_model)
        section.set_attribute([("id", "s", "custom-filter-section")])
        filter_model = self.text_filter_button.get_menu_model()
        replace_menu_section(filter_model, section)

    def on_widget_drag_drop(
        self,
        target: Gtk.DropTarget,
        value: Gdk.FileList,
        x: float,
        y: float,
        *data: Any,
    ) -> bool:
        files = value.get_files()
        if not files:
            return False

        self.open_paths(files)
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

            # On window close, this idle loop races widget destruction,
            # and so actions may already be gone at this point.
            stop_action = self.lookup_action('stop')
            if stop_action:
                stop_action.set_enabled(False)
        return pending

    def on_scheduler_runnable(self, sched):
        if not self.idle_hooked:
            self.spinner.show()
            self.spinner.start()
            self.lookup_action('stop').set_enabled(True)
            self.idle_hooked = GLib.idle_add(self.on_idle)

    @Gtk.Template.Callback()
    def on_close_request(self, window):
        if self.has_pages():
            self.should_close = True
            GLib.idle_add(self.close_window_async)

            # prevent close, will be done by thread if all pages are closed
            return True

        return False

    def close_window_async(self):
        # Delete pages from right-to-left.  This ensures that if a version
        # control page is open in the far left page, it will be closed last.
        if self.has_pages():
            page = self.tabview.get_nth_page(self.tabview.get_n_pages() - 1)
            self.tabview.set_selected_page(page)
            page.get_child().request_close()
        else:
            # all pages have been closed, close window
            self.close()

    def has_pages(self):
        return self.tabview.get_n_pages() > 0

    @Gtk.Template.Callback()
    def on_notify_selected_page(self, tabview: Adw.TabView, pspec):
        self.insert_action_group("view", None)
        for child in self.view_toolbar:
            self.view_toolbar.remove(child)

        newtab = tabview.get_selected_page()
        if not newtab:
            return

        newdoc = newtab.get_child()
        newdoc.on_container_switch_in_event(self)

        self.lookup_action('close').set_enabled(bool(newdoc))

        if hasattr(newdoc, 'scheduler'):
            self.scheduler.add_task(newdoc.scheduler)

        if hasattr(newdoc, 'toolbar_actions'):
            self.view_toolbar.append(newdoc.toolbar_actions)

    def action_new_tab(self, action, parameter):
        self.append_new_comparison()

    def action_close(self, *extra):
        if page := self.tabview.get_selected_page():
            page.request_close()

    def action_fullscreen_change(self, action, state):
        is_full = self.is_fullscreen()
        action.set_state(state)
        if state and not is_full:
            self.fullscreen()
        elif is_full:
            self.unfullscreen()

    def action_stop(self, *args):
        # TODO: This is the only window-level action we have that still
        # works on the "current" document like this.
        self.current_doc().action_stop()

    def page_removed(self, doc, status):
        if hasattr(doc, "scheduler"):
            self.scheduler.remove_scheduler(doc.scheduler)

        tabpage = self.tabview.get_page(doc)
        if tabpage.props.selected:
            self.insert_action_group("view", None)

        self.tabview.close_page(tabpage)
        removed_last_page = not self.has_pages()

        # Normal switch-page handlers don't get run for removing the
        # last page from a notebook.
        if removed_last_page:
            self.on_notify_selected_page(self.tabview, None)

        if self.should_close:
            if removed_last_page:
                cancelled = self.emit("close-request")
                if not cancelled:
                    self.destroy()
            else:
                GLib.idle_add(self.close_window_async)

    def on_page_state_changed(self, page, old_state, new_state):
        if self.should_close and old_state == ComparisonState.Closing:
            # Cancel closing if one of our tabs does
            self.should_close = False

    def on_file_changed(self, srcpage, filename):
        for page in self.tabview.get_pages():
            child = page.get_child()
            if child != srcpage:
                child.on_file_changed(filename)

    @Gtk.Template.Callback()
    def on_open_recent(self, recent_selector, uri):
        try:
            self.append_recent(uri)
        except (IOError, ValueError):
            # FIXME: Need error handling, but no sensible display location
            log.exception(f'Error opening recent file {uri}')

    def _append_page(self, doc):
        page = self.tabview.append(doc)
        doc.bind_property("tab-title", page, "title", BIND_DEFAULT_CREATE)
        doc.bind_property("tab-tooltip", page, "tooltip", BIND_DEFAULT_CREATE)

        # Change focus to the newly created page only if the user is on a
        # DirDiff or VcView page, or if it's a new tab page. This prevents
        # cycling through X pages when X diffs are initiated.
        if isinstance(self.current_doc(), DirDiff) or \
           isinstance(self.current_doc(), VcView) or \
           isinstance(doc, NewDiffTab):
            self.tabview.set_selected_page(self.tabview.get_page(doc))

        if hasattr(doc, "scheduler"):
            self.scheduler.add_scheduler(doc.scheduler)
        if isinstance(doc, MeldDoc):
            doc.file_changed_signal.connect(self.on_file_changed)
            doc.create_diff_signal.connect(
                lambda obj, arg, kwargs: self.append_diff(arg, **kwargs))
            doc.tab_state_changed.connect(self.on_page_state_changed)
        doc.close_signal.connect(self.page_removed)

    def append_new_comparison(self):
        doc = NewDiffTab(self)
        self._append_page(doc)

        def diff_created_cb(doc, newdoc):
            doc.request_close()
            self.tabview.set_selected_page(self.tabview.get_page(newdoc))

        doc.connect("diff-created", diff_created_cb)
        return doc

    def append_dirdiff(
        self,
        gfiles: Sequence[Optional[Gio.File]],
        auto_compare: bool = False,
    ) -> DirDiff:
        assert len(gfiles) in (1, 2, 3)
        doc = DirDiff(len(gfiles))
        self._append_page(doc)
        gfiles = [f or Gio.File.new_for_path("") for f in gfiles]
        doc.folders = gfiles
        doc.set_locations()
        if auto_compare:
            doc.scheduler.add_task(doc.auto_compare)
        return doc

    def append_filediff(
            self, gfiles, *, encodings=None, merge_output=None, meta=None):
        assert len(gfiles) in (1, 2, 3)

        # Check whether to show image window or not.
        if files_are_images(gfiles):
            doc = ImageDiff(len(gfiles))
        else:
            doc = FileDiff(len(gfiles))
        self._append_page(doc)
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
        doc = FileDiff(
            len(gfiles), comparison_mode=FileComparisonMode.AutoMerge)
        self._append_page(doc)
        doc.set_files(gfiles)
        if merge_output is not None:
            doc.set_merge_output_file(merge_output)
        return doc

    def append_diff(
        self,
        gfiles: Sequence[Optional[Gio.File]],
        auto_compare: bool = False,
        auto_merge: bool = False,
        merge_output: Optional[Gio.File] = None,
        meta: Optional[Dict[str, Any]] = None,
    ):
        have_directories = False
        have_files = False
        for f in gfiles:
            if not f:
                continue
            file_type = f.query_file_type(Gio.FileQueryInfoFlags.NONE, None)
            if file_type == Gio.FileType.DIRECTORY:
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
        self._append_page(doc)
        if isinstance(location, (list, tuple)):
            location = location[0]
        if location:
            doc.set_location(location.get_path())
        if auto_compare:
            doc.scheduler.add_task(doc.auto_compare)
        return doc

    def append_recent(self, uri):
        recent_comparisons = get_recent_comparisons()
        comparison_type, gfiles = recent_comparisons.read(uri)
        comparison_method = {
            RecentType.File: self.append_filediff,
            RecentType.Folder: self.append_dirdiff,
            RecentType.Merge: self.append_filemerge,
            RecentType.VersionControl: self.append_vcview,
        }
        tab = comparison_method[comparison_type](gfiles)
        self.tabview.set_selected_page(self.tabview.get_page(tab))
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
        doc.create_diff_signal.connect(
            lambda obj, arg, kwargs: self.append_diff(arg, **kwargs))
        doc.run_diff(path)

    def open_paths(self, gfiles, auto_compare=False, auto_merge=False,
                   focus=False):
        tab = None
        if len(gfiles) == 1:
            gfile = gfiles[0]
            if not gfile.query_exists():
                raise ValueError(_("Cannot compare a non-existent file"))

            if not gfile or (
                gfile.query_file_type(Gio.FileQueryInfoFlags.NONE, None)
                == Gio.FileType.DIRECTORY
            ):
                tab = self.append_vcview(gfile, auto_compare)
            else:
                self._single_file_open(gfile)

        elif len(gfiles) in (2, 3):
            tab = self.append_diff(gfiles, auto_compare=auto_compare,
                                   auto_merge=auto_merge)
        if tab:
            get_recent_comparisons().add(tab)
            if focus:
                self.tabview.set_selected_page(self.tabview.get_page(tab))

        return tab

    def current_doc(self):
        """Get the current doc or a dummy object if there is no current"""

        if page := self.tabview.get_selected_page():
            child = page.get_child()
            if isinstance(child, MeldDoc):
                return child

        class DummyDoc:
            def __getattr__(self, a):
                return lambda *x: None
        return DummyDoc()
