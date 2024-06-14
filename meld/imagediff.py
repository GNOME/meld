# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2009-2019 Kai Willadsen <kai.willadsen@gmail.com>
# Copyright (C) 2023 Martin van Zijl <martin.vanzijl@gmail.com>
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
from collections.abc import Sequence
from typing import Optional

from gi.repository import Gdk, GdkPixbuf, Gio, GLib, GObject, Gtk, GtkSource

# TODO: Don't from-import whole modules
from meld import misc
from meld.conf import _
from meld.const import FileComparisonMode
from meld.externalhelpers import open_files_external
from meld.melddoc import ComparisonState, MeldDoc
from meld.misc import with_focused_pane
from meld.settings import bind_settings
from meld.ui.util import map_widgets_into_lists

log = logging.getLogger(__name__)


# Cache the supported image MIME types.
_supported_mime_types: Optional[Sequence[str]] = None


def get_supported_image_mime_types() -> Sequence[str]:
    global _supported_mime_types

    if _supported_mime_types is None:
        # Get list of supported formats.
        _supported_mime_types = []
        supported_image_formats = GdkPixbuf.Pixbuf.get_formats()
        for image_format in supported_image_formats:
            _supported_mime_types += image_format.get_mime_types()

    return _supported_mime_types


def file_is_image(gfile):
    """Check if file is an image."""

    # Check for null value.
    if not gfile:
        return False

    # Check MIME type of the file.
    try:
        info = gfile.query_info(
            Gio.FILE_ATTRIBUTE_STANDARD_CONTENT_TYPE,
            Gio.FileQueryInfoFlags.NONE,
            None,
        )
        file_content_type = info.get_content_type()
        return file_content_type in get_supported_image_mime_types()
    except GLib.Error as err:
        if err.code == Gio.IOErrorEnum.NOT_FOUND:
            return False
        raise


def files_are_images(gfiles):
    """Check if all files in the list are images."""

    for gfile in gfiles:
        if not file_is_image(gfile):
            return False

    # All files are images.
    return True


@Gtk.Template(resource_path='/org/gnome/meld/ui/imagediff.ui')
class ImageDiff(Gtk.Box, MeldDoc):
    """Two or three way comparison of image files"""

    __gtype_name__ = "ImageDiff"

    close_signal = MeldDoc.close_signal
    create_diff_signal = MeldDoc.create_diff_signal
    file_changed_signal = MeldDoc.file_changed_signal
    label_changed = MeldDoc.label_changed
    tab_state_changed = MeldDoc.tab_state_changed

    scroll_window0 = Gtk.Template.Child()
    viewport0 = Gtk.Template.Child()
    image_event_box0 = Gtk.Template.Child()
    image_main0 = Gtk.Template.Child()
    scroll_window1 = Gtk.Template.Child()
    viewport1 = Gtk.Template.Child()
    image_event_box1 = Gtk.Template.Child()
    image_main1 = Gtk.Template.Child()
    scroll_window2 = Gtk.Template.Child()
    viewport2 = Gtk.Template.Child()
    image_event_box2 = Gtk.Template.Child()
    image_main2 = Gtk.Template.Child()

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

        self.files = [None, None, None]

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

        widget_lists = [
            "image_main",
            "image_event_box",
            "scroll_window",
            "viewport",
        ]
        map_widgets_into_lists(self, widget_lists)

        self.warned_bad_comparison = False
        self._keymask = 0
        self.meta = {}
        self.lines_removed = 0
        self.focus_pane = None

        # TODO: Add synchronized scrolling for large images.

        # Set up per-view action group for top-level menu insertion
        self.view_action_group = Gio.SimpleActionGroup()

        # Manually handle GAction additions
        # TODO: Highlight the selected image.
        actions = (
            ('copy-full-path', self.action_copy_full_path),
            ('open-external', self.action_open_external),
            ('open-folder', self.action_open_folder),
        )
        for name, callback in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', callback)
            self.view_action_group.add_action(action)

        builder = Gtk.Builder.new_from_resource(
            '/org/gnome/meld/ui/imagediff-menus.ui')
        self.popup_menu_model = builder.get_object('imagediff-context-menu')
        self.popup_menu = Gtk.Menu.new_from_model(self.popup_menu_model)
        self.popup_menu.attach_to_widget(self)

        builder = Gtk.Builder.new_from_resource(
            '/org/gnome/meld/ui/imagediff-actions.ui')
        self.toolbar_actions = builder.get_object('view-toolbar')
        self.copy_action_button = builder.get_object('copy_action_button')

        self.set_num_panes(num_panes)

    def set_files(self, gfiles, encodings=None):
        """Load the given files

        If an element is None, the text of a pane is left as is.
        """

        if len(gfiles) != self.num_panes:
            return

        encodings = encodings or ((None,) * len(gfiles))

        files = []
        for pane, (gfile, encoding) in enumerate(zip(gfiles, encodings)):
            if gfile:
                files.append((pane, gfile, encoding))

        for pane, gfile, encoding in files:
            self.load_file_in_pane(pane, gfile, encoding)

        # Update tab label.
        self.files = gfiles
        self.recompute_label()

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

        self.image_main[pane].set_from_file(gfile.get_path())

    def set_num_panes(self, n):
        if n == self.num_panes or n not in (1, 2, 3):
            return

        for widget in (
                self.image_main[:n] + self.image_event_box[:n] +
                self.scroll_window[:n] + self.viewport[:n]):
            widget.show()

        for widget in (
                self.image_main[n:] + self.image_event_box[n:] +
                self.scroll_window[n:] + self.viewport[n:]):
            widget.hide()

        self.num_panes = n

    def on_delete_event(self):
        self.state = ComparisonState.Closing
        self.close_signal.emit(0)
        return Gtk.ResponseType.OK

    def recompute_label(self):
        filenames = [f.get_path() for f in self.files if f]
        shortnames = misc.shorten_names(*filenames)

        label = self.meta.get("tablabel", "")
        if label:
            self.label_text = label
            tooltip_names = [label]
        else:
            self.label_text = " — ".join(shortnames)
            tooltip_names = filenames
        self.tooltip_text = "\n".join((_("File comparison:"), *tooltip_names))
        self.label_changed.emit(self.label_text, self.tooltip_text)

    @with_focused_pane
    def action_open_folder(self, pane, *args):
        gfile = self.files[pane]
        if not gfile:
            return

        parent = gfile.get_parent()
        if parent:
            open_files_external(gfiles=[parent])

    @with_focused_pane
    def action_open_external(self, pane, *args):
        gfile = self.files[pane]
        if not gfile:
            return

        gfiles = [gfile]
        open_files_external(gfiles=gfiles)

    @Gtk.Template.Callback()
    def on_imageview_popup_menu(self, imageview):
        self.popup_menu.popup_at_pointer()
        return True

    @Gtk.Template.Callback()
    def on_imageview_button_press_event(self, event_box, event):
        if event.button == 3:
            event_box.grab_focus()
            self.popup_menu.popup_at_pointer(event)
            return True
        return False

    def _get_focused_pane(self):
        for i in range(self.num_panes):
            if self.image_event_box[i].is_focus():
                return i
        return -1

    @with_focused_pane
    def action_copy_full_path(self, pane, *args):
        gfile = self.files[pane]
        if not gfile:
            return

        path = gfile.get_path() or gfile.get_uri()
        clip = Gtk.Clipboard.get_default(Gdk.Display.get_default())
        clip.set_text(path, -1)
        clip.store()

    def _set_external_action_sensitivity(self):
        # FIXME: This sensitivity is very confused. Essentially, it's always
        # enabled because we don't unset focus_pane, but the action uses the
        # current pane focus (i.e., _get_focused_pane) instead of focus_pane.
        have_file = self.focus_pane is not None
        self.set_action_enabled("open-external", have_file)

    @Gtk.Template.Callback()
    def on_imageview_focus_in_event(self, view, event):
        self.focus_pane = view
        self._set_external_action_sensitivity()

    @Gtk.Template.Callback()
    def on_imageview_focus_out_event(self, view, event):
        self._set_external_action_sensitivity()
