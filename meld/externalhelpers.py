import logging
import os
import shlex
import string
import subprocess
import sys
from typing import List, Optional, Sequence

from gi.repository import Gdk, Gio, GLib, Gtk

from meld.settings import settings

log = logging.getLogger(__name__)


def make_custom_editor_command(path: str, line: int = 0) -> Sequence[str]:
    custom_command = settings.get_string('custom-editor-command')
    fmt = string.Formatter()
    replacements = [tok[1] for tok in fmt.parse(custom_command)]

    if not any(replacements):
        return [custom_command, path]
    elif not all(r in (None, 'file', 'line') for r in replacements):
        log.error("Unsupported fields found")
        return [custom_command, path]
    else:
        cmd = custom_command.format(file=shlex.quote(path), line=line)
    return shlex.split(cmd)


def open_files_external(
    paths: Optional[List[str]] = None,
    *,
    gfiles: Optional[List[Gio.File]] = None,
    line: int = 0,
) -> None:
    def os_open(path: str, uri: str):
        if not path:
            return
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            Gtk.show_uri(Gdk.Screen.get_default(), uri, Gtk.get_current_event_time())

    def open_cb(source, result, *data):
        info = source.query_info_finish(result)
        file_type = info.get_file_type()
        path, uri = source.get_path(), source.get_uri()
        if file_type == Gio.FileType.DIRECTORY:
            os_open(path, uri)
        elif file_type == Gio.FileType.REGULAR:
            content_type = info.get_content_type()
            # FIXME: Content types are broken on Windows with current gio
            # If we can't access a content type, assume it's text.
            if not content_type or Gio.content_type_is_a(content_type, "text/plain"):
                if settings.get_boolean('use-system-editor'):
                    gfile = Gio.File.new_for_path(path)
                    if sys.platform == "win32":
                        handler = gfile.query_default_handler(None)
                        result = handler.launch([gfile], None)
                    else:
                        uri = gfile.get_uri()
                        Gio.AppInfo.launch_default_for_uri(uri, None)
                else:
                    editor = make_custom_editor_command(path, line)
                    if editor:
                        # TODO: If the editor is badly set up, this fails
                        # silently
                        subprocess.Popen(editor)
                    else:
                        os_open(path, uri)
            else:
                os_open(path, uri)
        else:
            # TODO: Add some kind of 'failed to open' notification
            pass

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
            None,
        )
