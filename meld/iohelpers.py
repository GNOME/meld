
from typing import Optional

from gi.repository import Gio, GLib, Gtk

from meld.conf import _
from meld.misc import get_modal_parent, modal_dialog
from meld.ui.filechooser import MeldFileChooserDialogFactory


def trash_or_confirm(gfile: Gio.File) -> bool:
    """Trash or delete the given Gio.File

    Files and folders will be moved to the system Trash location
    without confirmation. If they can't be trashed, then the user is
    prompted for an irreversible deletion.

    :rtype: bool
    :returns: whether the file was deleted
    """

    try:
        gfile.trash(None)
        return True
    except GLib.Error as e:
        # Handle not-supported, as that's due to the trashing target
        # being a (probably network) mount-point, not an underlying
        # problem. We also have to handle the generic FAILED code
        # because that's what we get with NFS mounts.
        expected_error = (
            e.code == Gio.IOErrorEnum.NOT_SUPPORTED or
            e.code == Gio.IOErrorEnum.FAILED
        )
        if not expected_error:
            raise RuntimeError(str(e))

    file_type = gfile.query_file_type(
        Gio.FileQueryInfoFlags.NONE, None)

    if file_type == Gio.FileType.DIRECTORY:
        raise RuntimeError(_("Deleting remote folders is not supported"))
    elif file_type != Gio.FileType.REGULAR:
        raise RuntimeError(_("Not a file or directory"))

    delete_permanently = modal_dialog(
        primary=_(
            "“{}” can’t be put in the trash. Do you want to "
            "delete it immediately?".format(
                GLib.markup_escape_text(gfile.get_parse_name()))
        ),
        secondary=_(
            "This remote location does not support sending items "
            "to the trash."
        ),
        buttons=[
            (_("_Cancel"), Gtk.ResponseType.CANCEL),
            (_("_Delete Permanently"), Gtk.ResponseType.OK),
        ],
    )

    if delete_permanently != Gtk.ResponseType.OK:
        return False

    try:
        gfile.delete(None)
        # TODO: Deleting remote folders involves reimplementing
        # shutil.rmtree for gio, and then calling
        # self.recursively_update().
    except Exception as e:
        raise RuntimeError(str(e))

    return True


def prompt_save_filename(
        title: str, parent: Optional[Gtk.Widget] = None) -> Optional[Gio.File]:

    dialog = MeldFileChooserDialogFactory.dialog(
        title,
        transient_for=get_modal_parent(parent),
        action=Gtk.FileChooserAction.SAVE,
    )
    dialog.set_default_response(Gtk.ResponseType.ACCEPT)
    response = dialog.run()
    gfile = dialog.get_file()
    dialog.destroy()

    if response != Gtk.ResponseType.ACCEPT or not gfile:
        return None

    try:
        file_info = gfile.query_info(
            'standard::name,standard::display-name',
            Gio.FileQueryInfoFlags.NONE,
            None,
        )
    except GLib.Error as err:
        if err.code == Gio.IOErrorEnum.NOT_FOUND:
            return gfile
        raise

    # The selected file exists, so we need to prompt for overwrite.
    parent_folder = gfile.get_parent()
    parent_name = parent_folder.get_parse_name() if parent_folder else ''
    file_name = file_info.get_display_name()

    replace = modal_dialog(
        primary=_("Replace file “%s”?") % file_name,
        secondary=_(
            "A file with this name already exists in “%s”.\n"
            "If you replace the existing file, its contents "
            "will be lost.") % parent_name,
        buttons=[
            (_("_Cancel"), Gtk.ResponseType.CANCEL),
            (_("_Replace"), Gtk.ResponseType.OK),
        ],
        messagetype=Gtk.MessageType.WARNING,
    )
    if replace != Gtk.ResponseType.OK:
        return None

    return gfile
