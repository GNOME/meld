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

from gi.repository import Gio
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango

from meld.conf import _
from meld.settings import meldsettings, settings
from meld.ui.gnomeglade import Component


class CommitDialog(GObject.GObject, Component):

    __gtype_name__ = "CommitDialog"

    break_commit_message = GObject.Property(type=bool, default=False)

    def __init__(self, parent):
        GObject.GObject.__init__(self)
        Component.__init__(self, "vcview.ui", "commitdialog")
        self.widget.set_transient_for(parent.widget.get_toplevel())
        selected = parent._get_selected_files()

        try:
            to_commit = parent.vc.get_files_to_commit(selected)
            topdir = parent.vc.root
            if to_commit:
                to_commit = ["\t" + s for s in to_commit]
            else:
                to_commit = ["\t" + _("No files will be committed")]
        except NotImplementedError:
            topdir = os.path.dirname(os.path.commonprefix(selected))
            to_commit = ["\t" + s[len(topdir) + 1:] for s in selected]
        self.changedfiles.set_text("(in %s)\n%s" %
                                   (topdir, "\n".join(to_commit)))

        self.textview.modify_font(meldsettings.font)
        commit_prefill = parent.vc.get_commit_message_prefill()
        if commit_prefill:
            buf = self.textview.get_buffer()
            buf.set_text(commit_prefill)
            buf.place_cursor(buf.get_start_iter())

        # Try and make the textview wide enough for a standard 80-character
        # commit message.
        context = self.textview.get_pango_context()
        metrics = context.get_metrics(meldsettings.font,
                                      context.get_language())
        char_width = metrics.get_approximate_char_width() / Pango.SCALE
        self.scrolledwindow1.set_size_request(80 * char_width, -1)

        settings.bind('vc-show-commit-margin', self.textview,
                      'show-right-margin', Gio.SettingsBindFlags.DEFAULT)
        settings.bind('vc-commit-margin', self.textview,
                      'right-margin-position', Gio.SettingsBindFlags.DEFAULT)
        settings.bind('vc-break-commit-message', self,
                      'break-commit-message', Gio.SettingsBindFlags.DEFAULT)
        self.widget.show_all()

    def run(self):
        self.previousentry.set_active(-1)
        self.textview.grab_focus()
        response = self.widget.run()
        msg = None
        if response == Gtk.ResponseType.OK:
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
        self.widget.destroy()
        return response, msg

    def on_previousentry_activate(self, gentry):
        idx = gentry.get_active()
        if idx != -1:
            model = gentry.get_model()
            buf = self.textview.get_buffer()
            buf.set_text(model[idx][1])


class PushDialog(Component):

    def __init__(self, parent):
        super().__init__("vcview.ui", "pushdialog")
        self.widget.set_transient_for(parent.widget.get_toplevel())
        self.widget.show_all()

    def run(self):
        # TODO: Ask the VC for a more informative label for what will happen.
        # In git, this is probably the parsed output of push --dry-run.

        response = self.widget.run()
        self.widget.destroy()
        return response
