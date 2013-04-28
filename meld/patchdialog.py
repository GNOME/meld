### Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
### Copyright (C) 2009-2010 Kai Willadsen <kai.willadsen@gmail.com>

### This program is free software; you can redistribute it and/or modify
### it under the terms of the GNU General Public License as published by
### the Free Software Foundation; either version 2 of the License, or
### (at your option) any later version.

### This program is distributed in the hope that it will be useful,
### but WITHOUT ANY WARRANTY; without even the implied warranty of
### MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
### GNU General Public License for more details.

### You should have received a copy of the GNU General Public License
### along with this program; if not, write to the Free Software
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
### USA.

import difflib
from gettext import gettext as _
import os

import gtk
import pango

from . import paths
from .ui import gnomeglade

from .util.compat import text_type
from .util.sourceviewer import srcviewer


class PatchDialog(gnomeglade.Component):

    def __init__(self, filediff):
        ui_file = paths.ui_dir("patch-dialog.ui")
        gnomeglade.Component.__init__(self, ui_file, "patchdialog")

        self.widget.set_transient_for(filediff.widget.get_toplevel())
        self.prefs = filediff.prefs
        self.prefs.notify_add(self.on_preference_changed)
        self.filediff = filediff

        buf = srcviewer.GtkTextBuffer()
        self.textview.set_buffer(buf)
        lang = srcviewer.get_language_from_mime_type("text/x-diff")
        srcviewer.set_language(buf, lang)
        srcviewer.set_highlight_syntax(buf, True)

        fontdesc = pango.FontDescription(self.prefs.get_current_font())
        self.textview.modify_font(fontdesc)
        self.textview.set_editable(False)

        self.index_map = {self.left_radiobutton: (0, 1),
                          self.right_radiobutton: (1, 2)}
        self.left_patch = True
        self.reverse_patch = self.reverse_checkbutton.get_active()

        if self.filediff.num_panes < 3:
            self.label3.hide()
            self.hbox2.hide()

    def on_preference_changed(self, key, value):
        if key == "use_custom_font" or key == "custom_font":
            fontdesc = pango.FontDescription(self.prefs.get_current_font())
            self.textview.modify_font(fontdesc)

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
                clip = gtk.clipboard_get()
                clip.set_text(txt)
                clip.store()
                break
            # Save patch as a file
            else:
                # FIXME: These filediff methods are actually general utility.
                filename = self.filediff._get_filename_for_saving(
                    _("Save Patch"))
                if filename:
                    self.filediff._save_text_to_filename(filename, txt)
                    break

        self.widget.hide()
