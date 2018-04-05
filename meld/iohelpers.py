
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import Gtk

from meld.conf import _
from meld.misc import modal_dialog


def trash_or_confirm(gfile: Gio.File):
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
    except GLib.GError as e:
        # Only handle not-supported, as that's due to trashing
        # the target mount-point, not an underlying problem.
        if e.code != Gio.IOErrorEnum.NOT_SUPPORTED:
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
