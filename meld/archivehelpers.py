import logging
import urllib.parse
from typing import Callable

from gi.repository import Gio, GLib

log = logging.getLogger(__name__)


# Content types that the gvfs archive:// mount should probably handle
ARCHIVE_CONTENT_TYPES = {
    "application/java-archive",
    "application/vnd.android.package-archive",
    "application/vnd.ms-cab-compressed",
    "application/x-7z-compressed",
    "application/x-archive",
    "application/x-bzip-compressed-tar",
    "application/x-cd-image",
    "application/x-compressed-tar",
    "application/x-cpio",
    "application/x-deb",
    "application/x-iso9660-image",
    "application/x-lha",
    "application/x-lzh-compressed",
    "application/x-lzma-compressed-tar",
    "application/x-rar",
    "application/x-rar-compressed",
    "application/x-rpm",
    "application/x-stuffit",
    "application/x-tar",
    "application/x-tarz",
    "application/x-xar",
    "application/x-xz-compressed-tar",
    "application/x-zip",
    "application/x-zip-compressed",
    "application/zip",
}

ARCHIVE_QUERY_ATTRS = ",".join(
    (
        Gio.FILE_ATTRIBUTE_STANDARD_TYPE,
        Gio.FILE_ATTRIBUTE_STANDARD_CONTENT_TYPE,
    )
)

_archive_mounts: set[Gio.Mount] = set()


def have_active_mounts() -> bool:
    return bool(_archive_mounts)


def is_archive(gfile: Gio.File | None) -> bool:
    if not gfile:
        return False

    try:
        info = gfile.query_info(ARCHIVE_QUERY_ATTRS, Gio.FileQueryInfoFlags.NONE, None)
    except GLib.Error as err:
        log.warning(f"Could not query file info for {gfile.get_uri()}: {err.message}")
        return False

    if info.get_file_type() != Gio.FileType.REGULAR:
        return False

    return info.get_content_type() in ARCHIVE_CONTENT_TYPES


def _make_archive_gfile(gfile: Gio.File) -> Gio.File:
    """Return a mountable Gio.File from the provided archive file"""
    uri = gfile.get_uri()
    encoded = urllib.parse.quote(urllib.parse.quote(uri, safe=""), safe="")
    return Gio.File.new_for_uri(f"archive://{encoded}/")


def mount_archive_async(
    gfile: Gio.File,
    callback: Callable[[Gio.File, Gio.File | None, GLib.Error | None], None],
) -> None:
    def _on_mount(source: Gio.File, result: Gio.AsyncResult) -> None:
        try:
            source.mount_enclosing_volume_finish(result)
        except GLib.Error as err:
            already_mounted = err.matches(
                Gio.io_error_quark(), Gio.IOErrorEnum.ALREADY_MOUNTED
            )
            if already_mounted:
                # Don't track archive mounts that we don't do ourselves. They
                # are someone else's responsibility to unmount, etc.
                callback(gfile, archive_gfile, None, allow_none=False)
                return
            log.error(f"Failed to mount archive {gfile.get_uri()}: {err.message}")
            callback(gfile, None, err, allow_none=False)
            return

        try:
            mount = source.find_enclosing_mount(None)
            _archive_mounts.add(mount)
        except GLib.Error as err:
            log.error(
                f"Failed to find archive mount: {err}; automatic unmount will fail"
            )

        callback(gfile, archive_gfile, None, allow_none=False)

    mount_operation = Gio.MountOperation()
    archive_gfile = _make_archive_gfile(gfile)
    archive_gfile.mount_enclosing_volume(
        Gio.MountMountFlags.NONE, mount_operation, None, _on_mount
    )


def unmount_archive_async(mount: Gio.Mount, callback: Callable[[], None]):
    def _on_unmount(source: Gio.File, result: Gio.AsyncResult) -> None:
        try:
            source.unmount_with_operation_finish(result)
        except GLib.Error as err:
            log.error(f"Failed to unmount archive {mount.get_name()}: {err.message}")
        # When called from the unmount-everything helper, this mount will have
        # already been removed. This discard is for more proactive unmounting.
        _archive_mounts.discard(mount)
        callback()

    log.info(f"Unmounting archive {mount.get_name()}")
    mount_operation = Gio.MountOperation()
    mount.unmount_with_operation(
        Gio.MountUnmountFlags.NONE, mount_operation, None, _on_unmount
    )


def unmount_archives(callback: Callable[[], None]) -> bool:
    mount = _archive_mounts.pop()
    # If we're on the last mount, we callback to the originally passed-in
    # callback. Otherwise we continue processing _archive_mounts.
    if _archive_mounts:
        unmount_archive_async(mount, lambda: unmount_archives(callback))
    else:
        unmount_archive_async(mount, callback)
