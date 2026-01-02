# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2010-2013 Kai Willadsen <kai.willadsen@gmail.com>
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

import os
import textwrap

from gi.repository import Adw, GObject, Gtk, Pango

from meld.conf import _
from meld.settings import settings


@Gtk.Template(resource_path="/org/gnome/meld/ui/commit-dialog.ui")
class CommitDialog(Adw.AlertDialog):
    __gtype_name__ = "CommitDialog"

    break_commit_message = GObject.Property(type=bool, default=False)

    changedfiles = Gtk.Template.Child()
    message_scrolled_window = Gtk.Template.Child()
    previousentry = Gtk.Template.Child()
    textview = Gtk.Template.Child()

    def __init__(self):
        super().__init__()

        # Try and make the textview wide enough for a standard 80-character
        # commit message.
        context = self.textview.get_pango_context()
        metrics = context.get_metrics(None, None)
        char_width = metrics.get_approximate_char_width() / Pango.SCALE
        width_request, height_request = self.message_scrolled_window.get_size_request()
        self.message_scrolled_window.set_size_request(80 * char_width, height_request)

        # 0 is Gio.SettingsBindFlags.DEFAULT
        settings.bind("vc-show-commit-margin", self.textview, "show-right-margin", 0)
        settings.bind("vc-commit-margin", self.textview, "right-margin-position", 0)
        settings.bind("vc-break-commit-message", self, "break-commit-message", 0)

    def run(self, parent, callback):
        selected = parent._get_selected_files()
        try:
            to_commit = parent.vc.get_files_to_commit(selected)
            if not to_commit:
                to_commit = [_("No files will be committed")]
        except NotImplementedError:
            topdir = os.path.dirname(os.path.commonprefix(selected))
            to_commit = [s[len(topdir) + 1 :] for s in selected]

        for line in to_commit:
            self.changedfiles.append(Gtk.Label(label=line, xalign=0.0))

        commit_prefill = parent.vc.get_commit_message_prefill()
        if commit_prefill:
            buf = self.textview.get_buffer()
            buf.set_text(commit_prefill)
            buf.place_cursor(buf.get_start_iter())

        self.previousentry.set_active(-1)
        self.textview.grab_focus()
        self.choose(parent, None, self.on_dialog_response, callback)

    def on_dialog_response(self, dialog, result, callback):
        response = dialog.choose_finish(result)
        if response != "commit":
            callback(False, None)
            return

        show_margin = self.textview.get_show_right_margin()
        margin = self.textview.get_right_margin_position()
        buf = self.textview.get_buffer()
        msg = buf.get_text(*buf.get_bounds(), include_hidden_chars=False)

        # This is a dependent option because of the margin column
        if show_margin and self.props.break_commit_message:
            paragraphs = msg.split("\n\n")
            msg = "\n\n".join(textwrap.fill(p, margin) for p in paragraphs)

        if msg.strip():
            self.previousentry.prepend_history(msg)

        callback(response, msg)

    @Gtk.Template.Callback()
    def on_previousentry_activate(self, gentry):
        idx = gentry.get_active()
        if idx != -1:
            model = gentry.get_model()
            buf = self.textview.get_buffer()
            buf.set_text(model[idx][1])
