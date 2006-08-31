### Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>

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

from __future__ import generators

import codecs
import math
import os
import re
import difflib
import struct

import pango
import gobject
import gtk
import gtk.keysyms

import diffutil
import gnomeglade
import misc
import melddoc
import paths

sourceview_available = 0

for sourceview in "gtksourceview sourceview".split():
    try:
        gsv = __import__(sourceview)
        sourceview_available = 1
        break
    except ImportError:
        pass

if sourceview_available:
    def set_highlighting_enabled(buf, fname, enabled):
        if enabled:
            import gnomevfs
            mime_type = gnomevfs.get_mime_type( os.path.abspath(fname) )
            man = gsv.SourceLanguagesManager()
            gsl = man.get_language_from_mime_type( mime_type )
            if gsl:
                buf.set_language(gsl)
            else:
                enabled = False
        buf.set_highlight(enabled)

gdk = gtk.gdk

################################################################################
#
# FileDiff
#
################################################################################

MASK_SHIFT, MASK_CTRL, MASK_ALT = 1, 2, 3

class FileDiff(melddoc.MeldDoc, gnomeglade.Component):
    """Two or three way diff of text files.
    """

    keylookup = {gtk.keysyms.Shift_L : MASK_SHIFT,
                 gtk.keysyms.Control_L : MASK_CTRL,
                 gtk.keysyms.Alt_L : MASK_ALT,
                 gtk.keysyms.Shift_R : MASK_SHIFT,
                 gtk.keysyms.Control_R : MASK_CTRL,
                 gtk.keysyms.Alt_R : MASK_ALT }

    def __init__(self, prefs, num_panes):
        """Start up an filediff with num_panes empty contents.
        """
        melddoc.MeldDoc.__init__(self, prefs)
        override = {}
        if sourceview_available:
            override["GtkTextView"] = gsv.SourceView
            override["GtkTextBuffer"] = gsv.SourceBuffer
        gnomeglade.Component.__init__(self, paths.share_dir("glade2/filediff.glade"), "filediff", override)
        self._map_widgets_into_lists( ["textview", "fileentry", "diffmap", "scrolledwindow", "linkmap", "statusimage"] )
        self._update_regexes()
        self.warned_bad_comparison = False
        if sourceview_available:
            for v in self.textview:
                v.set_buffer( gsv.SourceBuffer() )
                v.set_show_line_numbers(self.prefs.show_line_numbers)
        self.keymask = 0
        self.load_font()
        self.deleted_lines_pending = -1
        self.textview_overwrite = 0
        self.textview_focussed = None
        self.textview_overwrite_handlers = [ t.connect("toggle-overwrite", self.on_textview_toggle_overwrite) for t in self.textview ]
        for i in range(3):
            w = self.scrolledwindow[i]
            w.get_vadjustment().connect("value-changed", self._sync_vscroll )
            w.get_hadjustment().connect("value-changed", self._sync_hscroll )
        self._connect_buffer_handlers()
        self.linediffer = diffutil.Differ()
        for l in self.linkmap: # glade bug workaround
            l.set_events(gdk.BUTTON_PRESS_MASK | gdk.BUTTON_RELEASE_MASK )
            l.set_double_buffered(0) # we call paint_begin ourselves
        self.bufferdata = []
        for text in self.textview:
            text.set_wrap_mode( self.prefs.edit_wrap_lines )
            buf = text.get_buffer()
            self.bufferdata.append( MeldBufferData() )
            def add_tag(name, props):
                tag = buf.create_tag(name)
                for p,v in props.items():
                    tag.set_property(p,v)
            add_tag("edited line",   {"background": self.prefs.color_edited_bg,
                                      "foreground": self.prefs.color_edited_fg} )
            add_tag("delete line",   {"background": self.prefs.color_delete_bg,
                                      "foreground": self.prefs.color_delete_fg}  )
            add_tag("replace line",  {"background": self.prefs.color_replace_bg,
                                      "foreground": self.prefs.color_replace_fg} )
            add_tag("conflict line", {"background": self.prefs.color_conflict_bg,
                                      "foreground": self.prefs.color_conflict_fg} )
            add_tag("inline line",   {"background": self.prefs.color_inline_bg,
                                      "foreground": self.prefs.color_inline_fg} )
        class ContextMenu(gnomeglade.Component):
            def __init__(self, app):
                gladefile = paths.share_dir("glade2/filediff.glade")
                gnomeglade.Component.__init__(self, gladefile, "popup")
                self.parent = app
                self.pane = -1
            def popup_in_pane( self, pane ):
                self.pane = pane
                self.copy_left.set_sensitive( pane > 0 )
                self.copy_right.set_sensitive( pane+1 < self.parent.num_panes )
                self.widget.popup( None, None, None, 3, gtk.get_current_event_time() )
            def on_save_activate(self, menuitem):
                self.parent.save()
            def on_save_as_activate(self, menuitem):
                self.parent.save_file( self.pane, 1)
            def on_make_patch_activate(self, menuitem):
                self.parent.make_patch( self.pane )
            def on_cut_activate(self, menuitem):
                self.parent.on_cut_activate()
            def on_copy_activate(self, menuitem):
                self.parent.on_copy_activate()
            def on_paste_activate(self, menuitem):
                self.parent.on_paste_activate()
            def on_copy_left_activate(self, menuitem):
                self.parent.copy_selected(-1)
            def on_copy_right_activate(self, menuitem):
                self.parent.copy_selected(1)
            def on_edit_activate(self, menuitem):
                if self.parent.bufferdata[self.pane].filename:
                    self.parent._edit_files( [self.parent.bufferdata[self.pane].filename] )
        self.popup_menu = ContextMenu(self)
        self.find_dialog = None
        self.last_search = None
        self.set_num_panes(num_panes)
        gtk.idle_add( lambda *args: self.load_font()) # hack around Bug 316730

    def _update_regexes(self):
        self.regexes = []
        for r in [ misc.ListItem(i) for i in self.prefs.regexes.split("\n") ]:
            if r.active:
                try:
                    self.regexes.append( (re.compile(r.value+"(?m)"), r.value) )
                except re.error:
                    pass

    def _disconnect_buffer_handlers(self):
        for textview in self.textview:
            buf = textview.get_buffer()
            assert hasattr(buf,"handlers")
            textview.set_editable(0)
            for h in buf.handlers:
                buf.disconnect(h)

    def _connect_buffer_handlers(self):
        for textview in self.textview:
            buf = textview.get_buffer()
            textview.set_editable(1)
            id0 = buf.connect("insert-text", self.on_text_insert_text)
            id1 = buf.connect("delete-range", self.on_text_delete_range)
            id2 = buf.connect_after("insert-text", self.after_text_insert_text)
            id3 = buf.connect_after("delete-range", self.after_text_delete_range)
            buf.textview = textview
            buf.handlers = id0, id1, id2, id3

    def _update_cursor_status(self, buf):
        def update():
            it = buf.get_iter_at_mark( buf.get_insert() )
            # Abbreviation for insert,overwrite so that it will fit in the status bar
            insert_overwrite = _("INS,OVR").split(",")[ self.textview_overwrite ]
            # Abbreviation for line, column so that it will fit in the status bar
            line_column = _("Ln %i, Col %i") % (it.get_line()+1, it.get_line_offset()+1)
            status = "%s : %s" % ( insert_overwrite, line_column )
            self.emit("status-changed", status  )
            raise StopIteration; yield 0
        self.scheduler.add_task( update().next )

    def on_textbuffer_mark_set(self, buffer, it, mark):
        if mark.get_name() == "insert":
            self._update_cursor_status(buffer)
    def on_textview_focus_in_event(self, view, event):
        self.textview_focussed = view
        self._update_cursor_status(view.get_buffer())
    def on_switch_event(self):
        if self.textview_focussed:
            self.scheduler.add_task( self.textview_focussed.grab_focus )

    def _after_text_modified(self, buffer, startline, sizechange):
        if self.num_panes > 1:
            buffers = [t.get_buffer() for t in self.textview[:self.num_panes] ]
            pane = buffers.index(buffer)
            change_range = self.linediffer.change_sequence( pane, startline, sizechange, self._get_texts())
            for it in self._update_highlighting( change_range[0], change_range[1] ):
                pass
            self.queue_draw()
        self._update_cursor_status(buffer)

    def _get_texts(self, raw=0):
        class FakeText(object):
            def __init__(self, buf, textfilter):
                self.buf, self.textfilter = buf, textfilter
            def __getslice__(self, lo, hi):
                b = self.buf
                txt = b.get_text(b.get_iter_at_line(lo), b.get_iter_at_line(hi), 0)
                txt = self.textfilter(txt)
                return txt.split("\n")[:-1]
        class FakeTextArray(object):
            def __init__(self, bufs, textfilter):
                self.texts = [FakeText(b, textfilter) for b in  bufs]
            def __getitem__(self, i):
                return self.texts[i]
        return FakeTextArray( [t.get_buffer() for t in self.textview], [self._filter_text, lambda x:x][raw] )

    def _filter_text(self, txt):
        def killit(m):
            assert m.group().count("\n") == 0
            if len(m.groups()):
                s = m.group()
                for g in m.groups():
                    if g:
                        s = s.replace(g,"")
                return s
            else:
                return ""
        try:
            for c,r in self.regexes:
                txt = c.sub(killit,txt)
        except AssertionError:
            if not self.warned_bad_comparison:
                misc.run_dialog(_("Regular expression '%s' changed the number of lines in the file. " \
                    "Comparison will be incorrect. See the user manual for more details.") % r)
                self.warned_bad_comparison = True
        return txt

    def after_text_insert_text(self, buffer, it, newtext, textlen):
        lines_added = newtext.count("\n")
        starting_at = it.get_line() - lines_added
        self._after_text_modified(buffer, starting_at, lines_added)

    def after_text_delete_range(self, buffer, it0, it1):
        starting_at = it0.get_line()
        assert self.deleted_lines_pending != -1
        self._after_text_modified(buffer, starting_at, -self.deleted_lines_pending)
        self.deleted_lines_pending = -1

    def load_font(self):
        fontdesc = pango.FontDescription(self.prefs.get_current_font())
        context = self.textview0.get_pango_context()
        metrics = context.get_metrics( fontdesc, context.get_language() )
        self.pixels_per_line = (metrics.get_ascent() + metrics.get_descent()) / 1024
        self.pango_char_width = metrics.get_approximate_char_width()
        tabs = pango.TabArray(10, 0)
        tab_size = self.prefs.tab_size;
        for i in range(10):
            tabs.set_tab(i, pango.TAB_LEFT, i*tab_size*self.pango_char_width)
        for i in range(3):
            self.textview[i].modify_font(fontdesc)
            self.textview[i].set_tabs(tabs)
        for i in range(2):
            self.linkmap[i].queue_draw()
        load = lambda x: gnomeglade.load_pixbuf( paths.share_dir("glade2/pixmaps/"+x), self.pixels_per_line)
        self.pixbuf_apply0 = load("button_apply0.xpm")
        self.pixbuf_apply1 = load("button_apply1.xpm")
        self.pixbuf_delete = load("button_delete.xpm")
        self.pixbuf_copy0  = load("button_copy0.xpm")
        self.pixbuf_copy1  = load("button_copy1.xpm")

    def on_preference_changed(self, key, value):
        if key == "draw_style":
            for l in self.linkmap:
                l.queue_draw()
        elif key == "tab_size":
            tabs = pango.TabArray(10, 0)
            for i in range(10):
                tabs.set_tab(i, pango.TAB_LEFT, i*value*self.pango_char_width)
            for i in range(3):
                self.textview[i].set_tabs(tabs)
        elif key == "use_custom_font" or key == "custom_font":
            self.load_font()
        elif key == "show_line_numbers":
            if sourceview_available:
                for t in self.textview:
                    t.set_show_line_numbers( value )
        elif key == "use_syntax_highlighting":
            if sourceview_available:
                for i in range(self.num_panes):
                    set_highlighting_enabled(
                        self.textview[i].get_buffer(),
                        self.bufferdata[i].filename,
                        self.prefs.use_syntax_highlighting )
        elif key == "regexes":
            self._update_regexes()
        elif key == "edit_wrap_lines":
            [t.set_wrap_mode( self.prefs.edit_wrap_lines ) for t in self.textview]

    def on_key_press_event(self, object, event):
        x = self.keylookup.get(event.keyval, 0)
        if self.keymask | x != self.keymask:
            self.keymask |= x
            for l in self.linkmap[:self.num_panes-1]:
                a = l.get_allocation()
                w = self.pixbuf_copy0.get_width()
                l.queue_draw_area(0,      0, w, a[3])
                l.queue_draw_area(a[2]-w, 0, w, a[3])

    def on_key_release_event(self, object, event):
        x = self.keylookup.get(event.keyval, 0)
        if self.keymask & ~x != self.keymask:
            self.keymask &= ~x
            for l in self.linkmap[:self.num_panes-1]:
                a = l.get_allocation()
                w = self.pixbuf_copy0.get_width()
                l.queue_draw_area(0,      0, w, a[3])
                l.queue_draw_area(a[2]-w, 0, w, a[3])

    def is_modified(self):
        state = [b.modified for b in self.bufferdata]
        return 1 in state

    def _get_pane_label(self, i):
        return self.bufferdata[i].label or "<unnamed>"

    def on_delete_event(self, appquit=0):
        modified = [b.modified for b in self.bufferdata]
        if 1 in modified:
            dialog = gnomeglade.Component( paths.share_dir("glade2/filediff.glade"), "closedialog")
            dialog.widget.set_transient_for(self.widget.get_toplevel())
            buttons = []
            for i in range(self.num_panes):
                b = gtk.CheckButton( self._get_pane_label(i) )
                b.set_use_underline(False)
                buttons.append(b)
                dialog.box.pack_start(b, 1, 1)
                if not modified[i]:
                    b.set_sensitive(0)
                else:
                    b.set_active(1)
            dialog.box.show_all()
            if not appquit:
                dialog.button_quit.hide()
            response = dialog.widget.run()
            try_save = [ b.get_active() for b in buttons]
            dialog.widget.destroy()
            if response==gtk.RESPONSE_OK:
                for i in range(self.num_panes):
                    if try_save[i]:
                        if self.save_file(i) != melddoc.RESULT_OK:
                            return gtk.RESPONSE_CANCEL
            elif response==gtk.RESPONSE_CLOSE:
                return gtk.RESPONSE_CLOSE
            else:
                return gtk.RESPONSE_CANCEL
        return gtk.RESPONSE_OK

        #
        # text buffer undo/redo
        #
    def on_text_begin_user_action(self, *buffer):
        self.undosequence.begin_group()

    def on_text_end_user_action(self, *buffer):
        self.undosequence.end_group()

    def on_text_insert_text(self, buffer, it, text, textlen):
        if not self.undosequence_busy:
            self.undosequence.begin_group()
            pane = self.textview.index( buffer.textview )
            if self.bufferdata[pane].modified != 1:
                self.undosequence.add_action( BufferModifiedAction(buffer, self) )
            self.undosequence.add_action( BufferInsertionAction(buffer, it.get_offset(), text) )
            self.undosequence.end_group()

    def on_text_delete_range(self, buffer, it0, it1):
        text = buffer.get_text(it0, it1, 0)
        pane = self.textview.index(buffer.textview)
        assert self.deleted_lines_pending == -1
        self.deleted_lines_pending = text.count("\n")
        if not self.undosequence_busy:
            self.undosequence.begin_group()
            if self.bufferdata[pane].modified != 1:
                self.undosequence.add_action( BufferModifiedAction(buffer, self) )
            self.undosequence.add_action( BufferDeletionAction(buffer, it0.get_offset(), text) )
            self.undosequence.end_group()

        #
        #
        #

    def _get_focused_textview(self):
        for i in range(self.num_panes):
            t = self.textview[i]
            if t.is_focus():
                return t
        return None

    def on_find_activate(self, *args):
        self.keymask = 0
        self.queue_draw()
        if self.find_dialog:
            self.find_dialog.widget.present()
        else:
            class FindDialog(gnomeglade.Component):
                def __init__(self, app):
                    self.parent = app
                    self.pane = -1
                    gladefile = paths.share_dir("glade2/filediff.glade")
                    gnomeglade.Component.__init__(self, gladefile, "finddialog")
                    self.widget.set_transient_for(app.widget.get_toplevel())
                    self.widget.show_all()
                def on_destroy(self, *args):
                    self.parent.find_dialog = None
                    self.widget.destroy()
                def on_entry_search_for_activate(self, *args):
                    self.parent._find_text( self.entry_search_for.get_chars(0,-1),
                        self.check_case.get_active(),
                        self.check_word.get_active(),
                        self.check_wrap.get_active(),
                        self.check_regex.get_active() )
                    return 1
            self.find_dialog = FindDialog(self)

    def on_find_next_activate(self, *args):
        if self.last_search:
            s = self.last_search
            self._find_text(s.text, s.case, s.word, s.wrap, s.regex)
        else:
            self.on_find_activate()

    def on_copy_activate(self, *extra):
        t = self._get_focused_textview()
        if t:
            t.emit("copy-clipboard") #XXX .get_buffer().copy_clipboard()

    def on_cut_activate(self, *extra):
        t = self._get_focused_textview()
        if t:
            t.emit("cut-clipboard") #XXX get_buffer().cut_clipboard()

    def on_paste_activate(self, *extra):
        t = self._get_focused_textview()
        if t:
            t.emit("paste-clipboard") #XXX t.get_buffer().paste_clipboard(None, 1)

    def on_textview_button_press_event(self, textview, event):
        if event.button == 3:
            textview.grab_focus()
            pane = self.textview.index(textview)
            self.popup_menu.popup_in_pane( pane )
            return 1
        return 0

    def on_textview_toggle_overwrite(self, view):
        self.textview_overwrite = not self.textview_overwrite
        for v,h in zip(self.textview, self.textview_overwrite_handlers):
            v.disconnect(h)
            if v != view:
                v.emit("toggle-overwrite")
        self.textview_overwrite_handlers = [ t.connect("toggle-overwrite", self.on_textview_toggle_overwrite) for t in self.textview ]
        self._update_cursor_status(view.get_buffer())

        #
        # find/replace buffer
        #
    def _find_text(self, tofind_utf8, match_case=0, entire_word=0, wrap=1, regex=0):
        self.last_search = misc.struct(text=tofind_utf8, case=match_case, word=entire_word, wrap=wrap, regex=regex)
        view = self._get_focused_textview() or self.textview0
        buf = view.get_buffer()
        insert = buf.get_iter_at_mark( buf.get_insert() )
        tofind = tofind_utf8.decode("utf-8") # tofind is utf-8 encoded
        text = buf.get_text(*buf.get_bounds() ).decode("utf-8") # as is buffer
        if not regex:
            tofind = re.escape(tofind)
        if entire_word:
            tofind = r'\b' + tofind + r'\b'
        try:
            pattern = re.compile( tofind, (match_case and re.M or (re.M|re.I)) )
        except re.error, e:
            misc.run_dialog( _("Regular expression error\n'%s'") % e, self, messagetype=gtk.MESSAGE_ERROR)
        else:
            match = pattern.search(text, insert.get_offset()+1)
            if match == None and wrap:
                match = pattern.search(text, 0)
            if match:
                it = buf.get_iter_at_offset( match.start() )
                buf.place_cursor( it )
                it.forward_chars( match.end() - match.start() )
                buf.move_mark( buf.get_selection_bound(), it )
                view.scroll_to_mark( buf.get_insert(), 0)
            elif regex:
                misc.run_dialog( _("The regular expression '%s' was not found.") % tofind_utf8, self, messagetype=gtk.MESSAGE_INFO)
            else:
                misc.run_dialog( _("The text '%s' was not found.") % tofind_utf8, self, messagetype=gtk.MESSAGE_INFO)

        #
        # text buffer loading/saving
        #

    def set_labels(self, lst):
        assert len(lst) <= len(self.bufferdata)
        for l,d in zip(lst,self.bufferdata):
            if len(l): d.label = l

    def recompute_label(self):
        filenames = []
        for i in range(self.num_panes):
            filenames.append( self._get_pane_label(i) )
        shortnames = misc.shorten_names(*filenames)
        for i in range(self.num_panes):
            stock = None
            if self.bufferdata[i].modified == 1:
                shortnames[i] += "*"
                if self.bufferdata[i].writable == 1:
                    stock = gtk.STOCK_SAVE
                else:
                    stock = gtk.STOCK_SAVE_AS
            elif self.bufferdata[i].writable == 0:
                stock = gtk.STOCK_NO
            if stock:
                self.statusimage[i].show()
                self.statusimage[i].set_from_stock(stock, gtk.ICON_SIZE_SMALL_TOOLBAR)
            else:
                self.statusimage[i].hide()
        self.label_text = " : ".join(shortnames)
        self.label_changed()

    def set_files(self, files):
        """Set num panes to len(files) and load each file given.
           If an element is None, the text of a pane is left as is.
        """
        for i,f in enumerate(files):
            if f:
                b = self.textview[i].get_buffer()
                b.delete( b.get_start_iter(), b.get_end_iter() )
                absfile = os.path.abspath(f)
                self.fileentry[i].set_filename(absfile)
                bold, bnew = self.bufferdata[i], MeldBufferData(absfile)
                if bold.filename == bnew.filename:
                    bnew.label = bold.label
                self.bufferdata[i] = bnew
        self.recompute_label()
        self.scheduler.add_task( self._set_files_internal(files).next )

    def _set_files_internal(self, files):
        yield _("[%s] Set num panes") % self.label_text
        self.set_num_panes( len(files) )
        self._disconnect_buffer_handlers()
        self.linediffer.diffs = [[],[]]
        self.queue_draw()
        buffers = [t.get_buffer() for t in self.textview][:self.num_panes]
        try_codecs = self.prefs.text_codecs.split()
        yield _("[%s] Opening files") % self.label_text
        panetext = ["\n"] * self.num_panes
        tasks = []
        for i,f in enumerate(files):
            if f:
                try:
                    task = misc.struct(filename = f,
                                       file = codecs.open(f, "rU", try_codecs[0]),
                                       buf = buffers[i],
                                       codec = try_codecs[:],
                                       text = [],
                                       pane = i)
                    tasks.append(task)
                except (IOError, LookupError), e:
                    buffers[i].set_text("\n")
                    misc.run_dialog(
                        "%s\n\n%s\n%s" % (
                            _("Could not read from '%s'") % f,
                            _("The error was:"),
                            str(e)),
                        parent = self)
            else:
                panetext[i] = buffers[i].get_text( buffers[i].get_start_iter(), buffers[i].get_end_iter() )
        yield _("[%s] Reading files") % self.label_text
        while len(tasks):
            for t in tasks[:]:
                try:
                    nextbit = t.file.read(4096)
                    if nextbit.find("\x00") != -1:
                        misc.run_dialog(
                            "%s\n\n%s" % (
                                _("Could not read from '%s'") % t.filename,
                                _("It contains ascii nulls.\nPerhaps it is a binary file.") ),
                                parent = self )
                        t.buf.delete( t.buf.get_start_iter(), t.buf.get_end_iter() )
                        tasks.remove(t)
                except ValueError, err:
                    t.codec.pop(0)
                    if len(t.codec):
                        t.file = codecs.open(t.filename, "rU", t.codec[0])
                        t.buf.delete( t.buf.get_start_iter(), t.buf.get_end_iter() )
                        t.text = []
                    else:
                        print "codec error fallback", err
                        t.buf.delete( t.buf.get_start_iter(), t.buf.get_end_iter() )
                        misc.run_dialog(
                            "%s\n\n%s" % (
                                _("Could not read from '%s'") % t.filename,
                                _("I tried encodings %s.") % try_codecs ),
                            parent = self)
                        tasks.remove(t)
                except IOError, ioerr:
                    misc.run_dialog(
                        "%s\n\n%s\n%s" % (
                            _("Could not read from '%s'") % t.filename,
                            _("The error was:"),
                            str(ioerr)),
                        parent = self)
                    tasks.remove(t)
                else:
                    if len(nextbit):
                        t.buf.insert( t.buf.get_end_iter(), nextbit )
                        t.text.append(nextbit)
                    else:
                        self.set_buffer_writable(t.buf, os.access(t.filename, os.W_OK))
                        self.bufferdata[t.pane].encoding = t.codec[0]
                        if hasattr(t.file, "newlines"):
                            self.bufferdata[t.pane].newlines = t.file.newlines
                        tasks.remove(t)
                        panetext[t.pane] = "".join(t.text)
                        if len(panetext[t.pane]) and \
                            panetext[t.pane][-1] != "\n" and \
                            self.prefs.supply_newline:
                                t.buf.insert( t.buf.get_end_iter(), "\n")
                                panetext[t.pane] += "\n"
            yield 1
        self.undosequence.clear()
        yield _("[%s] Computing differences") % self.label_text
        panetext = [self._filter_text(p) for p in panetext]
        lines = map(lambda x: x.split("\n"), panetext)
        step = self.linediffer.set_sequences_iter(*lines)
        while step.next() == None:
            yield 1
        self.queue_draw()
        lenseq = [len(d) for d in self.linediffer.diffs]
        self.scheduler.add_task( self._update_highlighting( (0,lenseq[0]), (0,lenseq[1]) ).next )
        self._connect_buffer_handlers()
        if sourceview_available:
            for i in range(len(files)):
                if files[i]:
                    set_highlighting_enabled( self.textview[i].get_buffer(), files[i], self.prefs.use_syntax_highlighting )
        yield 0

    def _update_highlighting(self, range0, range1):
        buffers = [t.get_buffer() for t in self.textview]
        for b in buffers:
            taglist = ["delete line", "conflict line", "replace line", "inline line"]
            table = b.get_tag_table()
            for tagname in taglist:
                tag = table.lookup(tagname)
                b.remove_tag(tag, b.get_start_iter(), b.get_end_iter() )
        for chunk in self.linediffer.all_changes(self._get_texts()):
            for i,c in enumerate(chunk):
                if c and c[0] == "replace":
                    bufs = buffers[1], buffers[i*2]
                    #tags = [b.get_tag_table().lookup("replace line") for b in bufs]
                    starts = [b.get_iter_at_line(l) for b,l in zip(bufs, (c[1],c[3])) ]
                    text1 = "\n".join( self._get_texts(raw=1)[1  ][c[1]:c[2]] ).encode("utf16")
                    text1 = struct.unpack("%iH"%(len(text1)/2), text1)[1:]
                    textn = "\n".join( self._get_texts(raw=1)[i*2][c[3]:c[4]] ).encode("utf16")
                    textn = struct.unpack("%iH"%(len(textn)/2), textn)[1:]
                    matcher = difflib.SequenceMatcher(None, text1, textn)
                    #print "<<<\n%s\n---\n%s\n>>>" % (text1, textn)
                    tags = [b.get_tag_table().lookup("inline line") for b in bufs]
                    back = (0,0)
                    for o in matcher.get_opcodes():
                        if o[0] == "equal":
                            if (o[2]-o[1] < 3) or (o[4]-o[3] < 3):
                                back = o[4]-o[3], o[2]-o[1]
                            continue
                        for i in range(2):
                            s,e = starts[i].copy(), starts[i].copy()
                            s.forward_chars( o[1+2*i] - back[i] )
                            e.forward_chars( o[2+2*i] )
                            bufs[i].apply_tag(tags[i], s, e)
                        back = (0,0)
                    yield 1

    def on_textview_expose_event(self, textview, event):
        if self.num_panes == 1:
            return
        if event.window != textview.get_window(gtk.TEXT_WINDOW_TEXT) \
            and event.window != textview.get_window(gtk.TEXT_WINDOW_LEFT):
            return
        if not hasattr(textview, "meldgc"):
            self._setup_gcs(textview)
        visible = textview.get_visible_rect()
        pane = self.textview.index(textview)
        start_line = self._pixel_to_line(pane, visible.y)
        end_line = 1+self._pixel_to_line(pane, visible.y+visible.height)
        gc = lambda x : getattr(textview.meldgc, "gc_"+x)
        #gcdark = textview.get_style().black_gc
        gclight = textview.get_style().bg_gc[gtk.STATE_ACTIVE]
        #curline = textview.get_buffer().get_iter_at_mark( textview.get_buffer().get_insert() ).get_line()
               
        def draw_change(change): # draw background and thin lines
            ypos0 = self._line_to_pixel(pane, change[1]) - visible.y
            width = event.window.get_size()[0]
            #gcline = (gclight, gcdark)[change[1] <= curline and curline < change[2]]
            gcline = gclight
            event.window.draw_line(gcline, 0,ypos0-1, width,ypos0-1)
            if change[2] != change[1]:
                ypos1 = self._line_to_pixel(pane, change[2]) - visible.y
                event.window.draw_line(gcline, 0,ypos1, width,ypos1)
                event.window.draw_rectangle(gc(change[0]), 1, 0,ypos0, width,ypos1-ypos0)
        last_change = None
        for change in self.linediffer.single_changes(pane, self._get_texts()):
            if change[2] < start_line: continue
            if change[1] > end_line: break
            if last_change and change[1] <= last_change[2]:
                last_change = ("conflict", last_change[1], max(last_change[2],change[2]))
            else:
                if last_change:
                    draw_change(last_change)
                last_change = change
        if last_change:
            draw_change(last_change)
        
    def _get_filename_for_saving(self, title ):
        dialog = gtk.FileChooserDialog(title,
            parent=self.widget.get_toplevel(),
            action=gtk.FILE_CHOOSER_ACTION_SAVE,
            buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OK, gtk.RESPONSE_OK) )
        dialog.set_default_response(gtk.RESPONSE_OK)
        response = dialog.run()
        filename = None
        if response == gtk.RESPONSE_OK:
            filename = dialog.get_filename()
        dialog.destroy()
        if filename:
            if os.path.exists(filename):
                response = misc.run_dialog(
                    _('"%s" exists!\nOverwrite?') % os.path.basename(filename),
                    parent = self,
                    buttonstype = gtk.BUTTONS_YES_NO)
                if response == gtk.RESPONSE_NO:
                    return None
            return filename
        return None

    def _save_text_to_filename(self, filename, text):
        try:
            open(filename, "w").write(text)
        except IOError, e:
            misc.run_dialog(
                _("Error writing to %s\n\n%s.") % (filename, e),
                self, gtk.MESSAGE_ERROR, gtk.BUTTONS_OK)
            return False
        return True

    def save_file(self, pane, saveas=0):
        buf = self.textview[pane].get_buffer()
        bufdata = self.bufferdata[pane]
        if saveas or not bufdata.filename:
            filename = self._get_filename_for_saving( _("Choose a name for buffer %i.") % (pane+1) )
            if filename:
                bufdata.filename = bufdata.label = os.path.abspath(filename)
                self.fileentry[pane].set_filename( bufdata.filename)
            else:
                return melddoc.RESULT_ERROR
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), 0)
        if bufdata.newlines:
            if type(bufdata.newlines) == type(""):
                if(bufdata.newlines) != '\n':
                    text = text.replace("\n", bufdata.newlines)
            elif type(bufdata.newlines) == type(()):
                buttons = {'\n':("UNIX (LF)",0), '\r\n':("DOS (CR-LF)", 1), '\r':("MAC (CR)",2) }
                newline = misc.run_dialog( _("This file '%s' contains a mixture of line endings.\n\nWhich format would you like to use?") % bufdata.label,
                    self, gtk.MESSAGE_WARNING, buttonstype=gtk.BUTTONS_CANCEL,
                    extrabuttons=[ buttons[b] for b in bufdata.newlines ] )
                if newline < 0:
                    return
                for k,v in buttons.items():
                    if v[1] == newline:
                        bufdata.newlines = k
                        if k != '\n':
                            text = text.replace('\n', k)
                        break
        if bufdata.encoding and self.prefs.save_encoding==0:
            try:
                text = text.encode(bufdata.encoding)
            except UnicodeEncodeError:
                if misc.run_dialog(
                    _("'%s' contains characters not encodable with '%s'\nWould you like to save as UTF-8?") % (bufdata.label, bufdata.encoding),
                    self, gtk.MESSAGE_ERROR, gtk.BUTTONS_YES_NO) != gtk.RESPONSE_YES:
                    return melddoc.RESULT_ERROR
        if self._save_text_to_filename(bufdata.filename, text):
            self.emit("file-changed", bufdata.filename)
            self.undosequence.clear()
            self.set_buffer_modified(buf, 0)
            return melddoc.RESULT_OK
        else:
            return melddoc.RESULT_ERROR

    def make_patch(self, pane):
        fontdesc = pango.FontDescription(self.prefs.get_current_font())
        override = {}
        if sourceview_available:
            override["GtkTextView"] = gsv.SourceView
            override["GtkTextBuffer"] = gsv.SourceBuffer
        dialog = gnomeglade.Component( paths.share_dir("glade2/filediff.glade"), "patchdialog", override)
        dialog.widget.set_transient_for( self.widget.get_toplevel() )
        bufs = [t.get_buffer() for t in self.textview]
        texts = [b.get_text(*b.get_bounds()).split("\n") for b in bufs]
        texts[0] = [l+"\n" for l in texts[0]]
        texts[1] = [l+"\n" for l in texts[1]]
        names = [self._get_pane_label(i) for i in range(2)]
        prefix = os.path.commonprefix( names )
        try: prefixslash = prefix.rindex("/") + 1
        except ValueError: prefixslash = 0
        names = [n[prefixslash:] for n in names]
        if sourceview_available:
            dialog.textview.set_buffer( gsv.SourceBuffer() )
        dialog.textview.modify_font(fontdesc)
        buf = dialog.textview.get_buffer()
        lines = []
        for line in difflib.unified_diff(texts[0], texts[1], names[0], names[1]):
            buf.insert( buf.get_end_iter(), line )
            lines.append(line)
        if sourceview_available:
            man = gsv.SourceLanguagesManager()
            gsl = man.get_language_from_mime_type("text/x-diff")
            if gsl:
                buf.set_language(gsl)
                buf.set_highlight(True)
        result = dialog.widget.run()
        dialog.widget.destroy()
        if result >= 0:
            txt = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), 0)
            if result == 1: # copy
                clip = gtk.clipboard_get()
                clip.set_text(txt)
                clip.store()
            else:# save as
                filename = self._get_filename_for_saving( _("Save patch as...") )
                if filename:
                    self._save_text_to_filename(filename, txt)

    def set_buffer_writable(self, buf, yesno):
        pane = self.textview.index(buf.textview)
        self.bufferdata[pane].writable = yesno
        self.recompute_label()

    def set_buffer_modified(self, buf, yesno):
        pane = self.textview.index(buf.textview)
        self.bufferdata[pane].modified = yesno
        self.recompute_label()

    def save(self):
        pane = self._get_focused_pane()
        if pane >= 0:
            self.save_file(pane)

    def save_all(self):
        for i in range(self.num_panes):
            if self.bufferdata[i].modified:
                self.save_file(i)

    def on_fileentry_activate(self, entry):
        if self.on_delete_event() == gtk.RESPONSE_OK:
            files = [ e.get_full_path(0) for e in self.fileentry[:self.num_panes] ]
            self.set_files(files)
        return 1

    def _get_focused_pane(self):
        for i in range(self.num_panes):
            if self.textview[i].is_focus():
                return i
        return -1

    def copy_selected(self, direction):
        assert direction in (-1,1)
        src_pane = self._get_focused_pane()
        dst_pane = src_pane + direction
        assert dst_pane in range(self.num_panes)
        buffers = [t.get_buffer() for t in self.textview]
        text = buffers[src_pane].get_text( buffers[src_pane].get_start_iter(), buffers[src_pane].get_end_iter() )
        self.on_text_begin_user_action()
        buffers[dst_pane].set_text( text )
        self.on_text_end_user_action()
        self.scheduler.add_task( lambda : self._sync_vscroll( self.scrolledwindow[src_pane].get_vadjustment() ) and None )

        #
        # refresh and reload
        #
    def on_reload_activate(self, *extra):
        modified = [os.path.basename(b.label) for b in self.bufferdata if b.modified]
        if len(modified):
            message = _("Reloading will discard changes in:\n%s\n\nYou cannot undo this operation.") % "\n".join(modified)
            response = misc.run_dialog( message, parent=self, messagetype=gtk.MESSAGE_WARNING, buttonstype=gtk.BUTTONS_OK_CANCEL)
            if response != gtk.RESPONSE_OK:
                return
        files = [b.filename for b in self.bufferdata[:self.num_panes] ]
        self.set_files(files)

    def on_refresh_activate(self, *extra):
        files = [None for b in self.bufferdata[:self.num_panes] ]
        self.set_files(files)

    def queue_draw(self, junk=None):
        for i in range(self.num_panes-1):
            self.linkmap[i].queue_draw()
        self.diffmap0.queue_draw()
        self.diffmap1.queue_draw()

        #
        # scrollbars
        #
    def _sync_hscroll(self, adjustment):
        if not hasattr(self,"_sync_hscroll_lock"):
            self._sync_hscroll_lock = 0
        if not self._sync_hscroll_lock:
            self._sync_hscroll_lock = 1
            adjs = map( lambda x: x.get_hadjustment(), self.scrolledwindow)
            adjs.remove(adjustment)
            val = adjustment.get_value()
            for a in adjs:
                a.set_value(val)
            self._sync_hscroll_lock = 0

    def _sync_vscroll(self, adjustment):
        # only allow one scrollbar to be here at a time
        if not hasattr(self,"_sync_vscroll_lock"):
            self._sync_vscroll_lock = 0
        if not self._sync_vscroll_lock:
            self._sync_vscroll_lock = 1
            syncpoint = 0.5

            adjustments = map( lambda x: x.get_vadjustment(), self.scrolledwindow)
            adjustments = adjustments[:self.num_panes]
            master = adjustments.index(adjustment)
            # scrollbar influence 0->1->2 or 0<-1<-2 or 0<-1->2
            others = zip( range(self.num_panes), adjustments)
            del others[master]
            if master == 2:
                others.reverse()

            # the line to search for in the 'master' text
            master_y = adjustment.value + adjustment.page_size * syncpoint
            it = self.textview[master].get_line_at_y(master_y)[0]
            line_y, height = self.textview[master].get_line_yrange(it)
            line = it.get_line() + ((master_y-line_y)/height)

            for (i,adj) in others:
                mbegin,mend, obegin,oend = 0, self._get_line_count(master), 0, self._get_line_count(i)
                # look for the chunk containing 'line'
                for c in self.linediffer.pair_changes(master, i, self._get_texts()):
                    c = c[1:]
                    if c[0] >= line:
                        mend = c[0]
                        oend = c[2]
                        break
                    elif c[1] >= line:
                        mbegin,mend = c[0],c[1]
                        obegin,oend = c[2],c[3]
                        break
                    else:
                        mbegin = c[1]
                        obegin = c[3]
                fraction = (line - mbegin) / ((mend - mbegin) or 1)
                other_line = (obegin + fraction * (oend - obegin))
                it = self.textview[i].get_buffer().get_iter_at_line(other_line)
                val, height = self.textview[i].get_line_yrange(it)
                val -= (adj.page_size) * syncpoint
                val += (other_line-int(other_line)) * height
                val = misc.clamp(val, 0, adj.upper - adj.page_size)
                adj.set_value( val )

                # scrollbar influence 0->1->2 or 0<-1<-2 or 0<-1->2
                if master != 1:
                    line = other_line
                    master = 1
            self.on_linkmap_expose_event(self.linkmap0, None)
            self.on_linkmap_expose_event(self.linkmap1, None)
            self._sync_vscroll_lock = 0

        #
        # diffmap drawing
        #
    def on_diffmap_expose_event(self, area, event):
        diffmapindex = self.diffmap.index(area)
        textindex = (0, self.num_panes-1)[diffmapindex]

        #TODO need height of arrow button on scrollbar - how do we get that?
        size_of_arrow = 14
        hperline = float( self.scrolledwindow[textindex].get_allocation().height - 4*size_of_arrow) / self._get_line_count(textindex)
        if hperline > self.pixels_per_line:
            hperline = self.pixels_per_line

        scaleit = lambda x,s=hperline,o=size_of_arrow: x*s+o
        x0 = 4
        x1 = area.get_allocation().width - 2*x0

        window = area.window
        window.clear()
        gctext = area.get_style().text_gc[0]
        if not hasattr(area, "meldgc"):
            self._setup_gcs(area)

        gc = area.meldgc.get_gc
        for c in self.linediffer.single_changes(textindex, self._get_texts()):
            assert c[0] != "equal"
            outline = True
            if self.prefs.ignore_blank_lines:
                c1,c2 = self._consume_blank_lines( self._get_texts()[textindex][c[1]:c[2]] )
                if (c1 or c2) and (c[1]+c1 == c[2]-c2):
                    outline = False
            s,e = [int(x) for x in ( math.floor(scaleit(c[1])), math.ceil(scaleit(c[2]+(c[1]==c[2]))) ) ]
            window.draw_rectangle( gc(c[0]), 1, x0, s, x1, e-s)
            if outline: window.draw_rectangle( gctext, 0, x0, s, x1, e-s)

    def on_diffmap_button_press_event(self, area, event):
        #TODO need gutter of scrollbar - how do we get that?
        if event.button == 1:
            size_of_arrow = 14
            diffmapindex = self.diffmap.index(area)
            index = (0, self.num_panes-1)[diffmapindex]
            height = area.get_allocation().height
            fraction = (event.y - size_of_arrow) / (height - 3.75*size_of_arrow)
            adj = self.scrolledwindow[index].get_vadjustment()
            val = fraction * adj.upper - adj.page_size/2
            upper = adj.upper - adj.page_size
            adj.set_value( max( min(upper, val), 0) )
            return 1
        return 0

    def _get_line_count(self, index):
        """Return the number of lines in the buffer of textview 'text'"""
        return self.textview[index].get_buffer().get_line_count()

    def set_num_panes(self, n):
        if n != self.num_panes and n in (1,2,3):
            self.num_panes = n
            toshow =  self.scrolledwindow[:n] + self.fileentry[:n]
            toshow += self.linkmap[:n-1] + self.diffmap[:n]
            map( lambda x: x.show(), toshow )

            tohide =  self.statusimage + self.scrolledwindow[n:] + self.fileentry[n:]
            tohide += self.linkmap[n-1:] + self.diffmap[n:]
            map( lambda x: x.hide(), tohide )

            for i in range(self.num_panes):
                if self.bufferdata[i].modified:
                    self.statusimage[i].show()
            self.queue_draw()
            self.recompute_label()

    def _line_to_pixel(self, pane, line ):
        it = self.textview[pane].get_buffer().get_iter_at_line(line)
        return self.textview[pane].get_iter_location( it ).y

    def _pixel_to_line(self, pane, pixel ):
        return self.textview[pane].get_line_at_y( pixel )[0].get_line()

    def next_diff(self, direction):
        adjs = map( lambda x: x.get_vadjustment(), self.scrolledwindow)
        curline = self._pixel_to_line( 1, int(adjs[1].value + adjs[1].page_size/2) )
        c = None
        if direction == gdk.SCROLL_DOWN:
            for c in self.linediffer.single_changes(1, self._get_texts()):
                assert c[0] != "equal"
                c1,c2 = self._consume_blank_lines( self._get_texts()[1][c[1]:c[2]] )
                if c[1]+c1 == c[2]-c2:
                    continue
                if c[1] > curline + 1:
                    break
        else: #direction == gdk.SCROLL_UP
            for chunk in self.linediffer.single_changes(1, self._get_texts()):
                c1,c2 = self._consume_blank_lines( self._get_texts()[1][chunk[1]:chunk[2]] )
                if chunk[1]+c1 == chunk[2]-c2:
                    continue
                if chunk[2] < curline:
                    c = chunk
                elif c:
                    break
        if c:
            if c[2] - c[1]: # no range, use other side
                l0,l1 = c[1],c[2]
                aidx = 1
                a = adjs[aidx]
            else:
                l0,l1 = c[3],c[4]
                aidx = c[5]
                a = adjs[aidx]
            want = 0.5 * ( self._line_to_pixel(aidx, l0) + self._line_to_pixel(aidx,l1) - a.page_size )
            want = misc.clamp(want, 0, a.upper-a.page_size)
            a.set_value( want )

    def _setup_gcs(self, area):
        assert area.window
        gcd = area.window.new_gc()
        gcd.set_rgb_fg_color( gdk.color_parse(self.prefs.color_delete_bg) )
        gcc = area.window.new_gc()
        gcc.set_rgb_fg_color( gdk.color_parse(self.prefs.color_replace_bg) )
        gce = area.window.new_gc()
        gce.set_rgb_fg_color( gdk.color_parse(self.prefs.color_edited_bg) )
        gcx = area.window.new_gc()
        gcx.set_rgb_fg_color( gdk.color_parse(self.prefs.color_conflict_bg) )
        area.meldgc = misc.struct(gc_delete=gcd, gc_insert=gcd, gc_replace=gcc, gc_conflict=gcx)
        area.meldgc.get_gc = lambda p: getattr(area.meldgc, "gc_"+p)

    def _consume_blank_lines(self, txt):
        lo, hi = 0, 0
        for l in txt:
            if len(l)==0:
                lo += 1
            else:
                break
        for l in txt[lo:]:
            if len(l)==0:
                hi += 1
            else:
                break
        return lo,hi

        #
        # linkmap drawing
        #
    def on_linkmap_expose_event(self, area, event):
        window = area.window
        # not mapped?
        if not window: return
        if not hasattr(area, "meldgc"):
            self._setup_gcs(area)
        gctext = area.get_style().bg_gc[gtk.STATE_ACTIVE]

        alloc = area.get_allocation()
        (wtotal,htotal) = alloc.width, alloc.height
        window.begin_paint_rect( (0,0,wtotal,htotal) )
        window.clear()

        # gain function for smoothing
        #TODO cache these values
        bias = lambda x,g: math.pow(x, math.log(g) / math.log(0.5))
        def gain(t,g):
            if t<0.5:
                return bias(2*t,1-g)/2.0
            else:
                return (2-bias(2-2*t,1-g))/2.0
        f = lambda x: gain( x, 0.85)

        if self.keymask & MASK_SHIFT:
            pix0 = self.pixbuf_delete
            pix1 = self.pixbuf_delete
        elif self.keymask & MASK_CTRL:
            pix0 = self.pixbuf_copy0
            pix1 = self.pixbuf_copy1
        else: # self.keymask == 0:
            pix0 = self.pixbuf_apply0
            pix1 = self.pixbuf_apply1
        draw_style = self.prefs.draw_style
        gc = area.meldgc.get_gc

        which = self.linkmap.index(area)
        pix_start = [None] * self.num_panes
        pix_start[which  ] = self.textview[which  ].get_visible_rect().y
        pix_start[which+1] = self.textview[which+1].get_visible_rect().y

        def bounds(idx):
            return [self._pixel_to_line(idx, pix_start[idx]), self._pixel_to_line(idx, pix_start[idx]+htotal)]
        visible = [None] + bounds(which) + bounds(which+1)

        for c in self.linediffer.pair_changes(which, which+1, self._get_texts()):
            if self.prefs.ignore_blank_lines:
                c1,c2 = self._consume_blank_lines( self._get_texts()[which  ][c[1]:c[2]] )
                c3,c4 = self._consume_blank_lines( self._get_texts()[which+1][c[3]:c[4]] )
                c = c[0], c[1]+c1,c[2]-c2, c[3]+c3,c[4]-c4
                if c[1]==c[2] and c[3]==c[4]:
                    continue

            assert c[0] != "equal"
            if c[2] < visible[1] and c[4] < visible[3]: # find first visible chunk
                continue
            elif c[1] > visible[2] and c[3] > visible[4]: # we've gone past last visible
                break

            f0,f1 = [self._line_to_pixel(which,   l) - pix_start[which  ] for l in c[1:3] ]
            t0,t1 = [self._line_to_pixel(which+1, l) - pix_start[which+1] for l in c[3:5] ]

            if f0==f1: f0 -= 2; f1 += 2
            if t0==t1: t0 -= 2; t1 += 2
            if draw_style > 0:
                n = (1, 9)[draw_style-1]
                points0 = []
                points1 = []
                for t in map(lambda x: float(x)/n, range(n+1)):
                    points0.append( (int(    t*wtotal), int((1-f(t))*f0 + f(t)*t0 )) )
                    points1.append( (int((1-t)*wtotal), int(f(t)*f1 + (1-f(t))*t1 )) )

                points = points0 + points1 + [points0[0]]

                window.draw_polygon( gc(c[0]), 1, points)
                window.draw_lines(gctext, points0)
                window.draw_lines(gctext, points1)
            else:
                w = wtotal
                p = self.pixbuf_apply0.get_width()
                window.draw_polygon(gctext, 0, (( -1, f0), (  p, f0), (  p,f1), ( -1,f1)) )
                window.draw_polygon(gctext, 0, ((w+1, t0), (w-p, t0), (w-p,t1), (w+1,t1)) )
                points0 = (0,f0), (0,t0)
                window.draw_line( gctext, p, (f0+f1)/2, w-p, (t0+t1)/2 )

            x = wtotal-self.pixbuf_apply0.get_width()
            if c[0]=="insert":
                window.draw_pixbuf( gctext, pix1, 0,0, x, points0[-1][1], -1,-1, 0,0,0)
            elif c[0] == "delete":
                window.draw_pixbuf( gctext, pix0, 0,0, 0, points0[ 0][1], -1,-1, 0,0,0)
            else: #replace
                window.draw_pixbuf( gctext, pix0, 0,0, 0, points0[ 0][1], -1,-1, 0,0,0)
                window.draw_pixbuf( gctext, pix1, 0,0, x, points0[-1][1], -1,-1, 0,0,0)

        # allow for scrollbar at end of textview
        mid = 0.5 * self.textview0.get_allocation().height
        window.draw_line(gctext, int(.25*wtotal), int(mid), int(.75*wtotal), int(mid) )
        window.end_paint()

    def on_linkmap_scroll_event(self, area, event):
        self.next_diff(event.direction)

    def on_linkmap_button_press_event(self, area, event):
        if event.button == 1:
            self.focus_before_click = None
            for t in self.textview:
                if t.is_focus():
                    self.focus_before_click = t
                    break
            area.grab_focus()
            self.mouse_chunk = None
            alloc = area.get_allocation()
            (wtotal,htotal) = alloc.width, alloc.height
            pix_width = self.pixbuf_apply0.get_width()
            pix_height = self.pixbuf_apply0.get_height()
            if self.keymask == MASK_CTRL: # hack
                pix_height *= 2

            which = self.linkmap.index(area)

            # quick reject are we near the gutter?
            if event.x < pix_width:
                side = 0
                rect_x = 0
            elif event.x > wtotal - pix_width:
                side = 1
                rect_x = wtotal - pix_width
            else:
                return  1
            src = which + side
            dst = which + 1 - side
            adj = self.scrolledwindow[src].get_vadjustment()
            func = lambda c: self._line_to_pixel(src, c[1]) - adj.value

            for c in self.linediffer.pair_changes(src, dst, self._get_texts()):
                if self.prefs.ignore_blank_lines:
                    c1,c2 = self._consume_blank_lines( self._get_texts()[src][c[1]:c[2]] )
                    c3,c4 = self._consume_blank_lines( self._get_texts()[dst][c[3]:c[4]] )
                    c = c[0], c[1]+c1,c[2]-c2, c[3]+c3,c[4]-c4
                    if c[1]==c[2] and c[3]==c[4]:
                        continue
                if c[0] == "insert":
                    continue
                h = func(c)
                if h < 0: # find first visible chunk
                    continue
                elif h > htotal: # we've gone past last visible
                    break
                elif h < event.y and event.y < h + pix_height:
                    self.mouse_chunk = ( (src,dst), (rect_x, h, pix_width, pix_height), c)
                    break
            #print self.mouse_chunk
            return 1
        elif event.button == 2:
            self.linkmap_drag_coord = event.x
        return 0

    def on_linkmap_motion_notify_event(self, area, event):
        return
        #dx = event.x - self.linkmap_drag_coord
        #self.linkmap_drag_coord = event.x
        #w,h = self.scrolledwindow0.size_request()
        #w,h = size[2] - size[0], size[3] - size[1]
        #self.scrolledwindow0.set_size_request(w+dx,h)
        #print w+dx
        #textview0.get_allocation(
        #print misc.all(event)

    def on_linkmap_button_release_event(self, area, event):
        if event.button == 1:
            if self.focus_before_click:
                self.focus_before_click.grab_focus()
                self.focus_before_click = None
            if self.mouse_chunk:
                (src,dst), rect, chunk = self.mouse_chunk
                # check we're still in button
                inrect = lambda p, r: ((r[0] < p.x) and (p.x < r[0]+r[2]) and (r[1] < p.y) and (p.y < r[1]+r[3]))
                if inrect(event, rect):
                    # gtk tries to jump back to where the cursor was unless we move the cursor
                    self.textview[src].place_cursor_onscreen()
                    self.textview[dst].place_cursor_onscreen()
                    chunk = chunk[1:]
                    self.mouse_chunk = None

                    if self.keymask & MASK_SHIFT: # delete
                        b = self.textview[src].get_buffer()
                        b.delete(b.get_iter_at_line(chunk[0]), b.get_iter_at_line(chunk[1]))
                    elif self.keymask & MASK_CTRL: # copy up or down
                        b0 = self.textview[src].get_buffer()
                        t0 = b0.get_text( b0.get_iter_at_line(chunk[0]), b0.get_iter_at_line(chunk[1]), 0)
                        b1 = self.textview[dst].get_buffer()
                        if event.y - rect[1] < 0.5 * rect[3]: # copy up
                            b1.insert_with_tags_by_name(b1.get_iter_at_line(chunk[2]), t0, "edited line")
                        else: # copy down
                            b1.insert_with_tags_by_name(b1.get_iter_at_line(chunk[3]), t0, "edited line")
                    else: # replace
                        b0 = self.textview[src].get_buffer()
                        t0 = b0.get_text( b0.get_iter_at_line(chunk[0]), b0.get_iter_at_line(chunk[1]), 0)
                        b1 = self.textview[dst].get_buffer()
                        self.on_text_begin_user_action()
                        b1.delete(b1.get_iter_at_line(chunk[2]), b1.get_iter_at_line(chunk[3]))
                        b1.insert_with_tags_by_name(b1.get_iter_at_line(chunk[2]), t0, "edited line")
                        self.on_text_end_user_action()
            return 1
        return 0

    def on_linkmap_drag_begin(self, *args):
        print args

if gobject.pygtk_version < (2,8,0):
    gobject.type_register(FileDiff)

################################################################################
#
# Local Functions
#
################################################################################

class MeldBufferData(object):
    __slots__ = ("modified", "writable", "filename", "label", "encoding", "newlines")
    def __init__(self, filename=None):
        self.modified = 0
        self.writable = 1
        self.filename = filename
        self.label = filename
        self.encoding = None
        self.newlines = None

################################################################################
#
# BufferInsertionAction
#
################################################################################
class BufferInsertionAction(object):
    """A helper to undo/redo text insertion into a text buffer"""
    def __init__(self, buffer, offset, text):
        self.buffer = buffer
        self.offset = offset
        self.text = text
    def undo(self):
        b = self.buffer
        b.delete( b.get_iter_at_offset( self.offset), b.get_iter_at_offset(self.offset + len(self.text)) )
    def redo(self):
        b = self.buffer
        b.insert( b.get_iter_at_offset( self.offset), self.text)

################################################################################
#
# BufferDeletionAction
#
################################################################################
class BufferDeletionAction(object):
    """A helper to undo/redo text deletion from a text buffer"""
    def __init__(self, buffer, offset, text):
        self.buffer = buffer
        self.offset = offset
        self.text = text
    def undo(self):
        b = self.buffer
        b.insert( b.get_iter_at_offset( self.offset), self.text)
    def redo(self):
        b = self.buffer
        b.delete( b.get_iter_at_offset( self.offset), b.get_iter_at_offset(self.offset + len(self.text)) )
################################################################################
#
# BufferModifiedAction
#
################################################################################
class BufferModifiedAction(object):
    """A helper set modified flag on a text buffer"""
    def __init__(self, buffer, app):
        self.buffer, self.app = buffer, app
        self.app.set_buffer_modified(self.buffer, 1)
    def undo(self):
        self.app.set_buffer_modified(self.buffer, 0)
    def redo(self):
        self.app.set_buffer_modified(self.buffer, 1)

