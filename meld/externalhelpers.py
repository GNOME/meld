# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2011-2014, 2018-2019, 2024 Kai Willadsen <kai.willadsen@gmail.com>
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
import os
import shlex
import string
import subprocess
import sys
from typing import List, Mapping, Sequence

from gi.repository import Gio, GLib, Gtk

from meld.conf import _
from meld.misc import error_dialog
from meld.settings import get_settings

log = logging.getLogger(__name__)


OPEN_EXTERNAL_QUERY_ATTRS = ",".join(
    (
        Gio.FILE_ATTRIBUTE_STANDARD_TYPE,
        Gio.FILE_ATTRIBUTE_STANDARD_CONTENT_TYPE,
    )
)


def make_custom_editor_command(path: str, line: int = 0) -> Sequence[str]:
    custom_command = get_settings().get_string("custom-editor-command")
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


def launched_cb(launcher: Gtk.FileLauncher, result: Gio.AsyncResult, *data):
    try:
        launcher.launch_finish(result)
    except GLib.Error as err:
        # TODO: Replace with an alert AdwDialog or similar
        log.error(f"Failed to open {launcher.get_file().get_path()}: {err!s}")

def open_containing_folder_cb(launcher: Gtk.FileLauncher, result: Gio.AsyncResult, *data):
    try:
        launcher.open_containing_folder_finish(result)
    except GLib.Error as err:
        # TODO: Replace with an alert AdwDialog or similar
        log.error(f"Failed to open parent of {launcher.get_file().get_path()}: {err!s}")


def launch_with_default_handler(
    gfile: Gio.File, toplevel: Gtk.Widget | None, open_parent: bool = False
) -> None:
    # Ideally this function wouldn't exist, but the gtk_show_uri cross-platform
    # handling is less reliable than doing the below.
    if sys.platform in ("darwin", "win32") and not open_parent:
        path = gfile.get_path()
        if not path:
            log.warning(f"Couldn't open file {gfile.get_uri()}; no valid path")

        if sys.platform == "win32":
            os.startfile(gfile.get_path())
        else:  # sys.platform == "darwin"
            subprocess.Popen(["open", path])
    else:
        launcher = Gtk.FileLauncher(file=gfile)
        if open_parent:
            launcher.open_containing_folder(toplevel, None, open_containing_folder_cb, None)
        else:
            launcher.launch(toplevel, None, launched_cb, None)


def open_cb(
    gfile: Gio.File,
    result: Gio.AsyncResult,
    user_data: Mapping[str, int],
) -> None:
    info = gfile.query_info_finish(result)
    file_type = info.get_file_type()
    open_parent = user_data.get("open_parent", False)
    toplevel = user_data.get("toplevel")

    if file_type == Gio.FileType.DIRECTORY or open_parent:
        launch_with_default_handler(gfile, toplevel, open_parent=True)
    elif file_type == Gio.FileType.REGULAR:
        # If we can't access a content type, we assume it's text because
        # context types aren't reliably detected cross-platform.
        content_type = info.get_content_type()
        if not content_type or Gio.content_type_is_a(content_type, "text/plain"):
            if get_settings().get_boolean("use-system-editor"):
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
                        error_dialog(_("Failed to launch custom editor"), str(e))
                else:
                    launch_with_default_handler(gfile, toplevel)
        else:
            launch_with_default_handler(gfile, toplevel)
    else:
        # Being guarded about value_nick here, since it's probably not
        # exactly guaranteed API.
        file_type = getattr(file_type, "value_nick", "unknown")
        error_dialog(
            _("Unsupported file type"),
            _(f"External opening of files of type '{file_type}' is not supported"),
        )


def open_files_external(
    gfiles: List[Gio.File],
    *,
    line: int = 0,
    toplevel: Gtk.Widget | None = None,
    open_parent: bool = False,
) -> None:
    for f in gfiles:
        f.query_info_async(
            OPEN_EXTERNAL_QUERY_ATTRS,
            Gio.FileQueryInfoFlags.NONE,
            GLib.PRIORITY_LOW,
            None,
            open_cb,
            {"line": line, "toplevel": toplevel, "open_parent": open_parent},
        )
