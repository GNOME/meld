# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2009-2010, 2013 Kai Willadsen <kai.willadsen@gmail.com>
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

import difflib
import os

from gi.repository import Gtk
from gi.repository import GtkSource

from .ui import gnomeglade

from meld.conf import _
from meld.settings import meldsettings
from .util.compat import text_type
from meld.sourceview import LanguageManager


class PatchDialog(gnomeglade.Component):

    def __init__(self, filediff):
        gnomeglade.Component.__init__(self, "patch-dialog.ui", "patchdialog")

        self.widget.set_transient_for(filediff.widget.get_toplevel())
        self.filediff = filediff

        buf = GtkSource.Buffer()
        self.textview.set_buffer(buf)
        lang = LanguageManager.get_language_from_mime_type("text/x-diff")
        buf.set_language(lang)
        buf.set_highlight_syntax(True)

        self.textview.modify_font(meldsettings.font)
        self.textview.set_editable(False)

        self.index_map = {self.left_radiobutton: (0, 1),
                          self.right_radiobutton: (1, 2)}
        self.left_patch = True
        self.reverse_patch = self.reverse_checkbutton.get_active()

        if self.filediff.num_panes < 3:
            self.side_selection_label.hide()
            self.side_selection_box.hide()

        meldsettings.connect('changed', self.on_setting_changed)

    def on_setting_changed(self, setting, key):
        if key == "font":
            self.textview.modify_font(meldsettings.font)

    def on_buffer_selection_changed(self, radiobutton):
        if not radiobutton.get_active():
            return
        self.left_patch = radiobutton == self.left_radiobutton
        self.update_patch()

    def on_reverse_checkbutton_toggled(self, checkbutton):
        self.reverse_patch = checkbutton.get_active()
        self.update_patch()

    def update_patch(self):
        indices = (0, 1)
        if not self.left_patch:
            indices = (1, 2)
        if self.reverse_patch:
            indices = (indices[1], indices[0])

        texts = []
        for b in self.filediff.textbuffer:
            start, end = b.get_bounds()
            text = text_type(b.get_text(start, end, False), 'utf8')
            lines = text.splitlines(True)
            texts.append(lines)

        names = [self.filediff.textbuffer[i].data.label for i in range(3)]
        prefix = os.path.commonprefix(names)
        names = [n[prefix.rfind("/") + 1:] for n in names]

        buf = self.textview.get_buffer()
        text0, text1 = texts[indices[0]], texts[indices[1]]
        name0, name1 = names[indices[0]], names[indices[1]]
        diff_text = "".join(difflib.unified_diff(text0, text1, name0, name1))
        buf.set_text(diff_text)

    def run(self):
        self.update_patch()

        while 1:
            result = self.widget.run()
            if result < 0:
                break

            buf = self.textview.get_buffer()
            start, end = buf.get_bounds()
            txt = text_type(buf.get_text(start, end, False), 'utf8')

            # Copy patch to clipboard
            if result == 1:
                clip = Gtk.clipboard_get()
                clip.set_text(txt)
                clip.store()
                break
            # Save patch as a file
            else:
                # FIXME: These filediff methods are actually general utility.
                filename = self.filediff._get_filename_for_saving(
                    _("Save Patch"))
                if filename:
                    txt = txt.encode('utf-8')
                    self.filediff._save_text_to_filename(filename, txt)
                    break

        self.widget.hide()
