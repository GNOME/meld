### Copyright (C) 2002-2004 Stephen Kennedy <stevek@gnome.org>

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

import gconf
import gobject
import gtk
import re

import glade
import paths

class FindReplaceState:
    __slots__=("tofind", "toreplace", "match_case", "entire_word", "wrap_around", "use_regex", "replace_all")
    def __init__(self):
        for s in self.__slots__:
            setattr(self, s, None)


class FindReplaceDialog(gobject.GObject, glade.Component):
    
    STATE_ROOT = "/apps/meld/state/find"

    __gsignals__ = {
        "activate" : ( gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,) )
    }

    def __init__(self, parent):
        self.__gobject_init__()
        gladefile = paths.share_dir("glade2/filediff.glade")
        glade.Component.__init__(self, gladefile, "finddialog")
        self.entry_search_for = self.combo_search_for.child
        self.entry_replace_with = self.combo_replace_with.child
        self.combo_search_for.set_model( gtk.ListStore(type("")))
        self.combo_search_for.set_text_column(0)
        self.combo_replace_with.set_model( gtk.ListStore(type("")))
        self.combo_replace_with.set_text_column(0)
        self.gconf = gconf.client_get_default()
        self.update_history()
        self.connect_signal_handlers()
        self.toplevel.set_transient_for(parent)
        self.toplevel.show()
        for check in "match_case entire_word wrap_around use_regex".split():
            widget = getattr(self, "check_%s" % check)
            key = "%s/%s" % (self.STATE_ROOT, check)
            active = self.gconf.get_bool(key)
            widget.connect("toggled", lambda b,k=key : self.gconf.set_bool(k, b.get_active()) )
            widget.set_active(active)
        gtk.idle_add( lambda : self.entry_replace_with.select_region(0,-1) )
        gtk.idle_add( lambda : self.entry_search_for.select_region(0,-1) )

    def update_history(self):
        for entry,history_id in ( (self.entry_search_for,"search_for"),
                                  (self.entry_replace_with, "replace_with") ):
            history = self.gconf.get_list("%s/%s" % (self.STATE_ROOT, history_id), gconf.VALUE_STRING )
            name = entry.get_text()
            try:
                history.remove(name)
            except ValueError:
                pass
            while len(history) > 7:
                history.pop()
            if name:
                history.insert( 0, name )
            combo = entry.parent
            model = combo.get_model()
            model.clear()
            for h in history:
                model.append([h])
            if len(history):
                combo.set_active(0)
                self.gconf.set_list("%s/%s" % (self.STATE_ROOT, history_id), gconf.VALUE_STRING, history )

    def enable_search_replace(self):
        self.button_show_replace.hide()
        self.label_replace_with.show()
        self.combo_replace_with.show()
        self.button_replace_all.show()
        self.button_replace.show()

    def on_button_show_replace__clicked(self, *args):
        self.enable_search_replace()

    def on_check_use_regex__toggled(self, *args):
        self.label_regex.set_property("visible", self.check_use_regex.get_active() )
        self.on_entry_search_for__changed(self.entry_search_for)

    def on_entry_search_for__changed(self, entry):
        sensitive = True
        if self.check_use_regex.get_active():
            try:
                re.compile( entry.get_text() )
            except re.error, e:
                msg = _("%s") % str(e)
                self.label_regex.set_markup('<span color="red">%s</span>' % msg)
                sensitive = False
            else:
                self.label_regex.set_markup('')
        self.button_replace_all.set_sensitive(sensitive)
        self.button_replace.set_sensitive(sensitive)
        self.button_find.set_sensitive(sensitive)

    def on_entry_search_for__activate(self, *args):
        self.update_history()
        if self.combo_replace_with.get_property("visible"):
            self.entry_replace_with.grab_focus()
        elif self.button_find.get_property("sensitive"):
            self.on_button_find__clicked()

    def on_entry_replace_with__activate(self, *args):
        self.update_history()
        self.button_find.grab_focus()

    def _get_state(self, *args):
        s = FindReplaceState()
        s.tofind = self.entry_search_for.get_text().decode("utf-8") # widget chars utf-8 encoded
        s.toreplace = self.entry_replace_with.get_text().decode("utf-8") # widget chars utf-8 encoded
        s.match_case = self.check_match_case.get_active()
        s.entire_word = self.check_entire_word.get_active()
        s.wrap_around = self.check_wrap_around.get_active()
        s.use_regex = self.check_use_regex.get_active()
        return s

    def on_button_find__clicked(self, *args):
        self.update_history()
        s = self._get_state()
        s.toreplace = None
        self.emit("activate", s)

    def on_button_replace__clicked(self, *args):
        self.update_history()
        self.emit("activate", self._get_state())

    def on_button_replace_all__clicked(self, *args):
        self.update_history()
        s = self._get_state()
        s.replace_all = True
        self.emit("activate", s)

gobject.type_register(FindReplaceDialog)

def find_replace(state, buffer):
    tofind = state.tofind
    if not state.use_regex:
        tofind = re.escape(tofind)
    if state.entire_word:
        tofind = r'\b' + tofind + r'\b'
    pattern = re.compile( tofind, (state.match_case and re.M or (re.M|re.I)) )

    orig_cursor = buffer.create_mark( "orig_cursor", buffer.get_iter_at_mark( buffer.get_insert() ) )
    end_search = buffer.create_mark( "endsearch", buffer.get_end_iter(), True )

    done_something = False
    already_wrapped = False

    while 1:
        if buffer.get_selection_bounds():
            if pattern.match( buffer.get_text( *buffer.get_selection_bounds() ) ):
                if state.toreplace:
                    buffer.begin_user_action()
                    buffer.delete( *buffer.get_selection_bounds() )
                    buffer.insert_at_cursor( state.toreplace )
                    buffer.end_user_action()
                    done_something = True
                else:
                    buffer.place_cursor( buffer.get_selection_bounds()[1] )
        
        search_start = buffer.get_iter_at_mark( buffer.get_insert() )
        text = buffer.get_text( *buffer.get_bounds() )

        end_offset = buffer.get_iter_at_mark(end_search).get_offset()
        match = pattern.search( text, search_start.get_offset(), end_offset )
        if match == None and state.wrap_around and not already_wrapped:
            match = pattern.search( text, 0, end_offset )
            buffer.move_mark( end_search, buffer.get_iter_at_mark(orig_cursor) )
            already_wrapped = True
        if match:
            sel = buffer.get_iter_at_offset( match.start() )
            buffer.place_cursor( sel )
            sel.forward_chars( match.end() - match.start() )
            buffer.move_mark( buffer.get_selection_bound(), sel )
            done_something = True
        else:
            break
        if not state.replace_all:
            break
    buffer.delete_mark(orig_cursor)
    buffer.delete_mark(end_search)
    return done_something

