
from typing import Optional

from gi.repository import Gio, GObject, Gtk


class MeldFileButton(Gtk.Button):
    __gtype_name__ = "MeldFileButton"

    file: Optional[Gio.File] = GObject.Property(
        type=Gio.File,
        nick="Most recently selected file",
    )

    pane: int = GObject.Property(
        type=int,
        nick="Index of pane associated with this file selector",
        flags=(
            GObject.ParamFlags.READWRITE |
            GObject.ParamFlags.CONSTRUCT_ONLY
        ),
    )

    action: Gtk.FileChooserAction = GObject.Property(
        type=Gtk.FileChooserAction,
        nick="File selector action",
        flags=(
            GObject.ParamFlags.READWRITE |
            GObject.ParamFlags.CONSTRUCT_ONLY
        ),
        default=Gtk.FileChooserAction.OPEN,
    )

    local_only: bool = GObject.Property(
        type=bool,
        nick="Whether selected files should be limited to local file:// URIs",
        flags=(
            GObject.ParamFlags.READWRITE |
            GObject.ParamFlags.CONSTRUCT_ONLY
        ),
        default=True,
    )

    dialog_label: str = GObject.Property(
        type=str,
        nick="Label for the file selector dialog",
        flags=(
            GObject.ParamFlags.READWRITE |
            GObject.ParamFlags.CONSTRUCT_ONLY
        ),
    )

    @GObject.Signal('file-selected')
    def file_selected_signal(self, pane: int, file: Gio.File) -> None:
        ...

    icon_action_map = {
        Gtk.FileChooserAction.OPEN: "document-open-symbolic",
        Gtk.FileChooserAction.SELECT_FOLDER: "folder-open-symbolic",
    }

    def do_realize(self) -> None:
        Gtk.Button.do_realize(self)

        image = Gtk.Image.new_from_icon_name(
            self.icon_action_map[self.action], Gtk.IconSize.BUTTON)
        self.set_image(image)

    def do_clicked(self) -> None:
        dialog = Gtk.FileChooserNative(
            title=self.dialog_label,
            transient_for=self.get_toplevel(),
            action=self.action,
            local_only=self.local_only
        )

        if self.file and self.file.get_path():
            dialog.set_file(self.file)

        response = dialog.run()
        gfile = dialog.get_file()
        dialog.destroy()

        if response != Gtk.ResponseType.ACCEPT or not gfile:
            return

        self.file = gfile
        self.file_selected_signal.emit(self.pane, self.file)
