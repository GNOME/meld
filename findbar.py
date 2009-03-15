### Copyright (C) 2002-2009 Stephen Kennedy <stevek@gnome.org>

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
### Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import gnomeglade
import paths
import misc
import gtk
import re

def _(x): return x

class FindBar(gnomeglade.Component):
    def __init__(self):
        gnomeglade.Component.__init__(self, paths.share_dir("glade2/findbar.glade"), "findbar")
        gnomeglade.connect_signal_handlers(self)
        self.textview = None

    def hide(self):
        self.textview = None
        self.widget.hide()

    def start_find(self, textview):
        self.textview = textview
        self.replace_label.hide()
        self.replace_entry.hide()
        self.replace_button.hide()
        self.replace_all_button.hide()
        self.replace_filler.hide()
        self.widget.show()
        self.find_entry.grab_focus()

    def start_find_next(self, textview):
        self.textview = textview
        if self.find_entry.get_text():
            self.find_button.activate()
        else:
            self.start_find(self.textview)

    def start_replace(self, textview):
        self.textview = textview
        self.widget.show_all()
        self.find_entry.grab_focus()

    def on_find_entry__activate(self, entry):
        self.find_button.activate()

    def on_replace_entry__activate(self, entry):
        self.replace_button.activate()

    def on_find_button__activate(self, button):
        self._find_text()

    def on_replace_button__activate(self, entry):
        buf = self.textview.get_buffer()
        oldpos = buf.props.cursor_position
        self._find_text(0)
        if buf.props.cursor_position == oldpos:
            buf.begin_user_action()
            buf.delete_selection(False,False)
            buf.insert_at_cursor( self.replace_entry.get_text() )
            self._find_text( 0 )
            buf.end_user_action()

        #
        # find/replace buffer
        #
    def _find_text(self, start_offset=1):
        match_case = self.match_case.get_active()
        whole_word = self.whole_word.get_active()
        wrap = 1
        regex = self.regex.get_active()
        assert self.textview
        buf = self.textview.get_buffer()
        insert = buf.get_iter_at_mark( buf.get_insert() )
        tofind_utf8 = self.find_entry.get_text()
        tofind = tofind_utf8.decode("utf-8") # tofind is utf-8 encoded
        text = buf.get_text(*buf.get_bounds() ).decode("utf-8") # as is buffer
        if not regex:
            tofind = re.escape(tofind)
        if whole_word:
            tofind = r'\b' + tofind + r'\b'
        try:
            pattern = re.compile( tofind, (match_case and re.M or (re.M|re.I)) )
        except re.error, e:
            misc.run_dialog( _("Regular expression error\n'%s'") % e, self, messagetype=gtk.MESSAGE_ERROR)
        else:
            match = pattern.search(text, insert.get_offset() + start_offset)
            if match == None and wrap:
                match = pattern.search(text, 0)
            if match:
                it = buf.get_iter_at_offset( match.start() )
                buf.place_cursor( it )
                it.forward_chars( match.end() - match.start() )
                buf.move_mark( buf.get_selection_bound(), it )
                self.textview.scroll_to_mark(buf.get_insert(), 0.25)
            elif regex:
                misc.run_dialog( _("The regular expression '%s' was not found.") % tofind_utf8, self, messagetype=gtk.MESSAGE_INFO)
            else:
                misc.run_dialog( _("The text '%s' was not found.") % tofind_utf8, self, messagetype=gtk.MESSAGE_INFO)

def findbar_create(str1, str2, int1, int2):
    return FindBar().widget
