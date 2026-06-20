import pathlib
from typing import Optional, Sequence

from gi.repository import Adw, Gio, GLib, Gtk

from meld.conf import _
from meld.misc import get_modal_parent


def trash_or_confirm(
    gfile: Gio.File, callback, *, parent: Gtk.Widget | None = None
) -> None:
    """Trash or delete the given Gio.File

    Files and folders will be moved to the system Trash location
    without confirmation. If they can't be trashed, then the user is
    prompted for an irreversible deletion.

    :param gfile: The file to trash or delete
    """

    try:
        gfile.trash(None)
        callback(True)
        return
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

    file_type = gfile.query_file_type(Gio.FileQueryInfoFlags.NONE, None)

    if file_type == Gio.FileType.DIRECTORY:
        raise RuntimeError(_("Deleting remote folders is not supported"))
    elif file_type != Gio.FileType.REGULAR:
        raise RuntimeError(_("Not a file or directory"))

    def on_dialog_response(dialog, result):
        response = dialog.choose_finish(result)
        if response != "delete":
            callback(False)
            return

        try:
            gfile.delete(None)
            # TODO: Deleting remote folders involves reimplementing
            # shutil.rmtree for gio, and then calling
            # self.recursively_update().
            callback(True)
        except Exception as e:
            raise RuntimeError(str(e))

    filename = GLib.markup_escape_text(gfile.get_parse_name())

    dialog = Adw.AlertDialog(
        heading=_("Delete Permanently?"),
        body=_(
            f"“{filename}” can't be put in the trash. "
            "Do you want to delete it permanently?"
        ),
    )
    dialog.add_response("cancel", _("_Cancel"))
    dialog.add_response("delete", _("_Delete Permanently"))
    dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.set_default_response("cancel")
    dialog.set_close_response("cancel")
    dialog.choose(get_modal_parent(parent), None, on_dialog_response)


def prompt_save_filename(
        title: str,
        callback,
        *,
        parent: Optional[Gtk.Widget] = None
    ) -> None:

    def on_response(dialog: Gtk.FileChooserNative, response: int, callback):
        gfile = dialog.get_file()
        dialog.destroy()
        if response == Gtk.ResponseType.ACCEPT and gfile:
            callback(gfile)

    dialog = Gtk.FileChooserNative(
        title=title,
        transient_for=get_modal_parent(parent),
        action=Gtk.FileChooserAction.SAVE,
    )
    dialog.connect("response", on_response, callback)
    dialog.show()


def find_shared_parent_path(
    paths: Sequence[Optional[Gio.File]],
) -> Optional[Gio.File]:

    if not paths or not paths[0] or any(path is None for path in paths):
        return None

    current_parent = paths[0].get_parent()
    if len(paths) == 1:
        return current_parent

    while current_parent:
        is_valid_parent = all(
            current_parent.get_relative_path(path)
            for path in paths
        )
        if is_valid_parent:
            break

        current_parent = current_parent.get_parent()

    # Either we've broken out of the loop early, in which case we have
    # a valid common parent path, or we've fallen through, in which
    # case the path return is None.
    return current_parent


def format_home_relative_path(gfile: Gio.File) -> str:
    home_file = Gio.File.new_for_path(GLib.get_home_dir())
    home_relative = home_file.get_relative_path(gfile)
    if home_relative:
        return GLib.build_filenamev(['~', home_relative])
    else:
        return gfile.get_parse_name()


def format_parent_relative_path(parent: Gio.File, descendant: Gio.File) -> str:
    """Format shortened child paths using a common parent

    This is a helper for shortening sets of paths using their common
    parent as a guide for what is required to distinguish the paths
    from one another. The helper operates on every path individually,
    so that this work can be done in individual widgets using only the
    path being displayed (`descendent` here) and the common parent
    (`parent` here).
    """

    # When thinking about the segmentation we do here, there are
    # four path components that we care about:
    #
    #  * any path components above the non-common parent
    #  * the earliest non-common parent
    #  * any path components between the actual filename and the
    #    earliest non-common parent
    #  * the actual filename
    #
    # This is easiest to think about with an example of comparing
    # two files in a parallel repository structure (or similar).
    # Let's say that you have two copies of Meld at
    # /home/foo/checkouts/meld and /home/foo/checkouts/meld-new,
    # and you're comparing meld/filediff.py within those checkouts.
    # The components we want would then be (left to right):
    #
    #  ---------------------------------------------
    #  | /home/foo/checkouts | /home/foo/checkouts |
    #  | meld                | meld-new            |
    #  | meld                | meld                |
    #  | filediff.py         | filediff.py         |
    #  ---------------------------------------------
    #
    # Of all of these, the first (the first common parent) is the
    # *only* one that's actually guaranteed to be the same. The
    # second will *always* be different (or won't exist if e.g.,
    # you're comparing files in the same folder or similar). The
    # third component can be basically anything. The fourth
    # components will often be the same but that's not guaranteed.

    base_path_str = None
    immediate_parent_strs = []
    has_elided_path = False

    descendant_parent = descendant.get_parent()
    if descendant_parent is None:
        raise ValueError(f'Path {descendant.get_path()} has no parent')

    relative_path_str = parent.get_relative_path(descendant_parent)

    if relative_path_str:
        relative_path = pathlib.Path(relative_path_str)

        # We always try to leave the first and last path segments, to
        # try to handle e.g., <parent>/<project>/src/<module>/main.py.
        base_path_str = relative_path.parts[0]
        if len(relative_path.parts) > 1:
            immediate_parent_strs.append(relative_path.parts[-1])

        # As an additional heuristic, we try to include the second-last
        # path segment as well, to handle paths like e.g.,
        # <parent>/<some package structure>/<module>/src/main.py.
        # We only do this if the last component is short, to
        # handle src, dist, pkg, etc. without using too much space.
        if len(relative_path.parts) > 2 and len(immediate_parent_strs[0]) < 5:
            immediate_parent_strs.insert(0, relative_path.parts[-2])

        # We have elided paths if we have more parts than our immediate
        # parent count plus one for the base component.
        included_path_count = len(immediate_parent_strs) + 1
        has_elided_path = len(relative_path.parts) > included_path_count

    show_parent = not parent.has_parent()
    # It looks odd to have a single component, so if we don't have a
    # base path, we'll use the direct parent. In this case the parent
    # won't provide any disambiguation... it's just for appearances.
    if not show_parent and not base_path_str:
        base_path_str = parent.get_basename()

    label_segments = [
        '…' if not show_parent else None,
        base_path_str,
        '…' if has_elided_path else None,
        *immediate_parent_strs,
        descendant.get_basename(),
    ]
    label_text = format_home_relative_path(parent) if show_parent else ""
    label_text += GLib.build_filenamev([s for s in label_segments if s])

    return label_text


def is_file_on_tmpfs(gfile: Gio.File) -> bool:
    """Check whether a given file is on a tmpfs filesystem

    This is a Unix-specific operation. On any exception, this will
    return False.
    """
    try:
        path = gfile.get_path()
        if not path:
            return False

        mount, _timestamp = Gio.unix_mount_for(path)
        if not mount:
            return False

        return Gio.unix_mount_get_fs_type(mount) == "tmpfs"
    except Exception:
        return False
