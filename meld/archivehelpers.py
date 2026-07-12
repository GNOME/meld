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
    callback: Callable[[Gio.File | None, GLib.Error | None], None],
) -> None:
    def _on_mount(source: Gio.File, result: Gio.AsyncResult) -> None:
        try:
            source.mount_enclosing_volume_finish(result)
        except GLib.Error as err:
            already_mounted = err.matches(
                Gio.io_error_quark(), Gio.IOErrorEnum.ALREADY_MOUNTED
            )
            if already_mounted:
                callback(archive_gfile, None, allow_none=False)
                return
            log.warning(f"Failed to mount archive {gfile.get_uri()}: {err.message}")
            callback(None, err, allow_none=False)
            return
        callback(archive_gfile, None, allow_none=False)

    mount_operation = Gio.MountOperation()
    archive_gfile = _make_archive_gfile(gfile)
    archive_gfile.mount_enclosing_volume(
        Gio.MountMountFlags.NONE, mount_operation, None, _on_mount
    )
