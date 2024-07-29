
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
        self.set_icon_name(self.icon_action_map[self.action])

    def do_clicked(self) -> None:
        dialog = Gtk.FileChooserNative(
            title=self.dialog_label,
            transient_for=self.get_native(),
            action=self.action,
        )

        if self.file and self.file.get_path():
            dialog.set_file(self.file)

        dialog.connect("response", self.on_dialog_response)
        dialog.show()
        # Maintain a reference to the dialog until we get a response
        self.dialog = dialog

    def on_dialog_response(self, dialog: Gtk.FileChooserNative, response: Gtk.ResponseType, *user_data):
        gfile = dialog.get_file()

        if response != Gtk.ResponseType.ACCEPT or not gfile:
            return

        self.file = gfile
        self.file_selected_signal.emit(self.pane, self.file)
        del self.dialog
