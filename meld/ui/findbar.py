### Copyright (C) 2002-2009 Stephen Kennedy <stevek@gnome.org>
### Copyright (C) 2012 Kai Willadsen <kai.willadsen@gmail.com>

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

import gtk
import re

from meld import misc
from meld import paths
from . import gnomeglade

from gettext import gettext as _

class FindBar(gnomeglade.Component):
    def __init__(self, parent):
        gnomeglade.Component.__init__(self, paths.ui_dir("findbar.ui"),
                                      "findbar", ["arrow_left", "arrow_right"])
        gnomeglade.connect_signal_handlers(self)
        self.textview = None
        self.orig_base_color = self.find_entry.get_style().base[0]
        self.arrow_left.show()
        self.arrow_right.show()
        parent.connect('set-focus-child', self.on_focus_child)

    def on_focus_child(self, container, widget):
        if widget is not None:
            # TODO: Not in PyGtk 2.16; remove this check later
            if hasattr(self.widget, "get_visible"):
                visible = self.widget.get_visible()
            else:
                visible = self.widget.props.visible
            if widget is not self.widget and visible:
                self.hide()
        return False

    def hide(self):
        self.textview = None
        self.wrap_box.hide()
        self.widget.hide()

    def start_find(self, textview, text=None):
        self.textview = textview
        self.replace_label.hide()
        self.replace_entry.hide()
        self.hbuttonbox2.hide()
        if text:
            self.find_entry.set_text(text)
        self.widget.set_row_spacings(0)
        self.widget.show()
        self.find_entry.grab_focus()

    def start_find_next(self, textview):
        self.textview = textview
        if self.find_entry.get_text():
            self.find_next_button.activate()
        else:
            self.start_find(self.textview)

    def start_find_previous(self, textview, text=None):
        self.textview = textview
        if self.find_entry.get_text():
            self.find_previous_button.activate()
        else:
            self.start_find(self.textview)

    def start_replace(self, textview, text=None):
        self.textview = textview
        if text:
            self.find_entry.set_text(text)
        self.widget.set_row_spacings(6)
        self.widget.show_all()
        self.find_entry.grab_focus()
        self.wrap_box.hide()

    def on_find_entry__activate(self, entry):
        self.find_next_button.activate()

    def on_replace_entry__activate(self, entry):
        self.replace_button.activate()

    def on_find_next_button__clicked(self, button):
        self._find_text()

    def on_find_previous_button__clicked(self, button):
        self._find_text(backwards=True)

    def on_replace_button__clicked(self, entry):
        buf = self.textview.get_buffer()
        oldsel = buf.get_selection_bounds()
        match = self._find_text(0)
        newsel = buf.get_selection_bounds()
        # only replace if there is a match at the cursor and it was already selected
        if match and oldsel and oldsel[0].equal(newsel[0]) and oldsel[1].equal(newsel[1]):
            buf.begin_user_action()
            buf.delete_selection(False,False)
            buf.insert_at_cursor( self.replace_entry.get_text() )
            self._find_text( 0 )
            buf.end_user_action()

    def on_replace_all_button__clicked(self, entry):
        buf = self.textview.get_buffer()
        saved_insert = buf.create_mark(None, buf.get_iter_at_mark(buf.get_insert()), True)
        buf.begin_user_action()
        while self._find_text(0):
            buf.delete_selection(False,False)
            buf.insert_at_cursor( self.replace_entry.get_text() )
        buf.end_user_action()
        if not saved_insert.get_deleted():
            buf.place_cursor( buf.get_iter_at_mark(saved_insert) )
            self.textview.scroll_to_mark(buf.get_insert(), 0.25)

    def on_find_entry__changed(self, entry):
        entry.modify_base( gtk.STATE_NORMAL, self.orig_base_color )

        #
        # find/replace buffer
        #
    def _find_text(self, start_offset=1, backwards=False, wrap=True):
        match_case = self.match_case.get_active()
        whole_word = self.whole_word.get_active()
        regex = self.regex.get_active()
        assert self.textview
        buf = self.textview.get_buffer()
        insert = buf.get_iter_at_mark( buf.get_insert() )
        tofind_utf8 = self.find_entry.get_text()
        tofind = tofind_utf8.decode("utf-8") # tofind is utf-8 encoded
        start, end = buf.get_bounds()
        text = buf.get_text(start, end, False).decode("utf-8") # as is buffer
        if not regex:
            tofind = re.escape(tofind)
        if whole_word:
            tofind = r'\b' + tofind + r'\b'
        try:
            pattern = re.compile( tofind, (match_case and re.M or (re.M|re.I)) )
        except re.error as e:
            misc.run_dialog( _("Regular expression error\n'%s'") % e, self, messagetype=gtk.MESSAGE_ERROR)
        else:
            self.wrap_box.hide()
            if backwards == False:
                match = pattern.search(text, insert.get_offset() + start_offset)
                if match is None and wrap:
                    self.wrap_box.show()
                    match = pattern.search(text, 0)
            else:
                match = None
                for m in pattern.finditer(text, 0, insert.get_offset()):
                    match = m
                if match is None and wrap:
                    self.wrap_box.show()
                    for m in pattern.finditer(text, insert.get_offset()):
                        match = m
            if match:
                it = buf.get_iter_at_offset( match.start() )
                buf.place_cursor( it )
                it.forward_chars( match.end() - match.start() )
                buf.move_mark( buf.get_selection_bound(), it )
                self.textview.scroll_to_mark(buf.get_insert(), 0.25)
                return True
            else:
                buf.place_cursor( buf.get_iter_at_mark(buf.get_insert()) )
                self.find_entry.modify_base(gtk.STATE_NORMAL, gtk.gdk.color_parse("#ffdddd"))
                self.wrap_box.hide()
