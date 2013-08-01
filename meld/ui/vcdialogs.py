# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2010-2013 Kai Willadsen <kai.willadsen@gmail.com>

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.

from __future__ import print_function

import os
import textwrap
from gettext import gettext as _

import gtk
import pango

from meld import misc
from meld import paths
from . import gnomeglade


# FIXME: Duplication from vcview
def _commonprefix(files):
    if len(files) != 1:
        workdir = misc.commonprefix(files)
    else:
        workdir = os.path.dirname(files[0]) or "."
    return workdir


class CommitDialog(gnomeglade.Component):

    def __init__(self, parent):
        gnomeglade.Component.__init__(self, paths.ui_dir("vcview.ui"),
                                      "commitdialog")
        self.parent = parent
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
            topdir = _commonprefix(selected)
            to_commit = ["\t" + s[len(topdir) + 1:] for s in selected]
        self.changedfiles.set_text("(in %s)\n%s" %
                                   (topdir, "\n".join(to_commit)))

        fontdesc = pango.FontDescription(self.parent.prefs.get_current_font())
        self.textview.modify_font(fontdesc)
        commit_prefill = self.parent.vc.get_commit_message_prefill()
        if commit_prefill:
            buf = self.textview.get_buffer()
            buf.set_text(commit_prefill)
            buf.place_cursor(buf.get_start_iter())

        # Try and make the textview wide enough for a standard 80-character
        # commit message.
        context = self.textview.get_pango_context()
        metrics = context.get_metrics(fontdesc, context.get_language())
        char_width = metrics.get_approximate_char_width()
        self.textview.set_size_request(80 * pango.PIXELS(char_width), -1)

        self.widget.show_all()

    def run(self):
        prefs = self.parent.prefs
        margin = prefs.vc_commit_margin
        self.textview.set_right_margin_position(margin)
        self.textview.set_show_right_margin(prefs.vc_show_commit_margin)

        self.previousentry.set_active(-1)
        self.textview.grab_focus()
        response = self.widget.run()
        if response == gtk.RESPONSE_OK:
            buf = self.textview.get_buffer()
            msg = buf.get_text(*buf.get_bounds(), include_hidden_chars=False)
            # This is a dependent option because of the margin column
            if prefs.vc_show_commit_margin and prefs.vc_break_commit_message:
                paragraphs = msg.split("\n\n")
                msg = "\n\n".join(textwrap.fill(p, margin) for p in paragraphs)
            self.parent._command_on_selected(
                self.parent.vc.commit_command(msg))
            if msg.strip():
                self.previousentry.prepend_history(msg)
        self.widget.destroy()

    def on_previousentry_activate(self, gentry):
        idx = gentry.get_active()
        if idx != -1:
            model = gentry.get_model()
            buf = self.textview.get_buffer()
            buf.set_text(model[idx][1])


class PushDialog(gnomeglade.Component):

    def __init__(self, parent):
        gnomeglade.Component.__init__(self, paths.ui_dir("vcview.ui"),
                                      "pushdialog")
        self.parent = parent
        self.widget.set_transient_for(parent.widget.get_toplevel())
        self.widget.show_all()

    def run(self):
        # TODO: Ask the VC for a more informative label for what will happen.
        # In git, this is probably the parsed output of push --dry-run.

        response = self.widget.run()
        if response == gtk.RESPONSE_OK:
            self.parent.vc.push(self.parent._command)
        self.widget.destroy()
