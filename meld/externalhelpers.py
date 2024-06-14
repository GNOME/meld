import logging
import os
import shlex
import string
import subprocess
import sys
from typing import List, Optional, Sequence

from gi.repository import Gdk, Gio, GLib, Gtk

from meld.conf import _
from meld.misc import modal_dialog
from meld.settings import settings

log = logging.getLogger(__name__)


def make_custom_editor_command(path: str, line: int = 0) -> Sequence[str]:
    custom_command = settings.get_string("custom-editor-command")
    fmt = string.Formatter()
    replacements = [tok[1] for tok in fmt.parse(custom_command)]

    if not any(replacements):
        return [custom_command, path]
    elif not all(r in (None, "file", "line") for r in replacements):
        log.error("Unsupported fields found")
        return [custom_command, path]
    else:
        cmd = custom_command.format(file=shlex.quote(path), line=line)
    return shlex.split(cmd)


def launch_with_default_handler(gfile: Gio.File) -> None:
    # Ideally this function wouldn't exist, but the gtk_show_uri cross-platform
    # handling is less reliable than doing the below.
    if sys.platform in ("darwin", "win32"):
        path = gfile.get_path()
        if not path:
            log.warning(f"Couldn't open file {gfile.get_uri()}; no valid path")

        if sys.platform == "win32":
            os.startfile(gfile.get_path())
        else:  # sys.platform == "darwin"
            subprocess.Popen(["open", path])
    else:
        Gtk.show_uri(
            Gdk.Screen.get_default(),
            gfile.get_uri(),
            Gtk.get_current_event_time(),
        )


def open_cb(gfile: Gio.File, result, user_data) -> None:
    info = gfile.query_info_finish(result)
    file_type = info.get_file_type()

    if file_type == Gio.FileType.DIRECTORY:
        launch_with_default_handler(gfile)
    elif file_type == Gio.FileType.REGULAR:
        content_type = info.get_content_type()
        # FIXME: Content types are broken on Windows with current gio
        # If we can't access a content type, assume it's text.
        if not content_type or Gio.content_type_is_a(content_type, "text/plain"):
            if settings.get_boolean("use-system-editor"):
                if sys.platform == "win32":
                    handler = gfile.query_default_handler(None)
                    result = handler.launch([gfile], None)
                else:
                    Gio.AppInfo.launch_default_for_uri(gfile.get_uri(), None)
            else:
                line = user_data.get("line", 0)
                path = gfile.get_path()
                editor = make_custom_editor_command(path, line)
                if editor:
                    try:
                        subprocess.Popen(editor)
                    except OSError as e:
                        modal_dialog(
                            _("Failed to launch custom editor"),
                            str(e),
                            Gtk.ButtonsType.CLOSE,
                        )
                else:
                    launch_with_default_handler(gfile)
        else:
            launch_with_default_handler(gfile)
    else:
        # Being guarded about value_nick here, since it's probably not
        # exactly guaranteed API.
        file_type = getattr(file_type, "value_nick", "unknown")
        modal_dialog(
            _("Unsupported file type"),
            _("External opening of files of type {file_type} is not supported").format(
                file_type=file_type
            ),
            Gtk.ButtonsType.CLOSE,
        )


def open_files_external(
    paths: Optional[List[str]] = None,
    *,
    gfiles: Optional[List[Gio.File]] = None,
    line: int = 0,
) -> None:
    query_attrs = ",".join(
        (Gio.FILE_ATTRIBUTE_STANDARD_TYPE, Gio.FILE_ATTRIBUTE_STANDARD_CONTENT_TYPE)
    )

    if not gfiles:
        gfiles = [Gio.File.new_for_path(s) for s in paths]

    for f in gfiles:
        f.query_info_async(
            query_attrs,
            Gio.FileQueryInfoFlags.NONE,
            GLib.PRIORITY_LOW,
            None,
            open_cb,
            {"line": line},
        )
