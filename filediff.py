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

import codecs
import os
from gettext import gettext as _
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
import cairo

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
            mime_type = gnomevfs.get_mime_type( 
                    gnomevfs.make_uri_from_input(os.path.abspath(fname)) )
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

MASK_SHIFT, MASK_CTRL = 1, 2

class FileDiff(melddoc.MeldDoc, gnomeglade.Component):
    """Two or three way diff of text files.
    """

    keylookup = {gtk.keysyms.Shift_L : MASK_SHIFT,
                 gtk.keysyms.Control_L : MASK_CTRL,
                 gtk.keysyms.Shift_R : MASK_SHIFT,
                 gtk.keysyms.Control_R : MASK_CTRL}

    def __init__(self, prefs, num_panes):
        """Start up an filediff with num_panes empty contents.
        """
        melddoc.MeldDoc.__init__(self, prefs)
        override = {}
        if sourceview_available:
            override["GtkTextView"] = gsv.SourceView
            override["GtkTextBuffer"] = gsv.SourceBuffer
        gnomeglade.Component.__init__(self, paths.share_dir("glade2/filediff.glade"), "filediff", override)
        self.map_widgets_into_lists( ["textview", "fileentry", "diffmap", "scrolledwindow", "linkmap", "statusimage"] )
        for d in self.diffmap: d.hide()
        self._update_regexes()
        self.warned_bad_comparison = False
        if sourceview_available:
            for v in self.textview:
                v.set_buffer( gsv.SourceBuffer() )
                v.set_show_line_numbers(self.prefs.show_line_numbers)
                v.set_insert_spaces_instead_of_tabs(self.prefs.spaces_instead_of_tabs)
                v.set_tabs_width(self.prefs.tab_size)
        self.keymask = 0
        self.load_font()
        self.deleted_lines_pending = -1
        self.textview_overwrite = 0
        self.textview_focussed = None
        self.textview_overwrite_handlers = [ t.connect("toggle-overwrite", self.on_textview_toggle_overwrite) for t in self.textview ]
        self.textbuffer = [v.get_buffer() for v in self.textview]
        self.bufferdata = [MeldBufferData() for b in self.textbuffer]
        for i in range(3):
            w = self.scrolledwindow[i]
            w.get_vadjustment().connect("value-changed", self._sync_vscroll )
            w.get_hadjustment().connect("value-changed", self._sync_hscroll )
            w.get_vscrollbar().connect_after("expose-event", self.on_vscroll__expose_event)
        self._connect_buffer_handlers()
        self._sync_vscroll_lock = False
        self._sync_hscroll_lock = False
        self.linediffer = diffutil.Differ()
        for text in self.textview:
            text.set_wrap_mode( self.prefs.edit_wrap_lines )
        for buf in self.textbuffer:
            buf.create_tag("edited line",   background = self.prefs.color_edited_bg,
                                            foreground = self.prefs.color_edited_fg)
            buf.create_tag("delete line",   background = self.prefs.color_delete_bg,
                                            foreground = self.prefs.color_delete_fg)
            buf.create_tag("replace line",  background = self.prefs.color_replace_bg,
                                            foreground = self.prefs.color_replace_fg)
            buf.create_tag("conflict line", background = self.prefs.color_conflict_bg,
                                            foreground = self.prefs.color_conflict_fg)
            buf.create_tag("inline line",   background = self.prefs.color_inline_bg,
                                            foreground = self.prefs.color_inline_fg)

        def parse_to_cairo(color_spec):
            color = gdk.color_parse(color_spec)
            return [x / 65535. for x in (color.red, color.green, color.blue)]

        self.fill_colors = {"insert"   : parse_to_cairo(self.prefs.color_delete_bg),
                            "delete"   : parse_to_cairo(self.prefs.color_delete_bg),
                            "conflict" : parse_to_cairo(self.prefs.color_conflict_bg),
                            "replace"  : parse_to_cairo(self.prefs.color_replace_bg)}

        darken = lambda color: [x * 0.8 for x in color]
        self.line_colors = {"insert"   : darken(self.fill_colors["insert"]),
                            "delete"   : darken(self.fill_colors["delete"]),
                            "conflict" : darken(self.fill_colors["conflict"]),
                            "replace"  : darken(self.fill_colors["replace"])}

        actions = (
            ("FileOpen",          gtk.STOCK_OPEN,       None,            None, _("Open selected"), self.on_open_activate),
            ("CreatePatch",       None,                 _("Create Patch"),  None, _("Create a patch"), self.make_patch),
            ("CopyAllLeft",       gtk.STOCK_GOTO_FIRST, _("Copy To Left"),  None, _("Copy all changes from right pane to left pane"), lambda x: self.copy_selected(-1)),
            ("CopyAllRight",      gtk.STOCK_GOTO_LAST,  _("Copy To Right"), None, _("Copy all changes from left pane to right pane"), lambda x: self.copy_selected(1)),
        )

        self.ui_file = paths.share_dir("glade2/filediff-ui.xml")
        self.actiongroup = gtk.ActionGroup('FilediffPopupActions')
        self.actiongroup.set_translation_domain("meld")
        self.actiongroup.add_actions(actions)
        self.find_dialog = None
        self.last_search = None
        self.set_num_panes(num_panes)
        gobject.idle_add( lambda *args: self.load_font()) # hack around Bug 316730

    def on_container_switch_in_event(self, ui):
        melddoc.MeldDoc.on_container_switch_in_event(self, ui)
        if self.textview_focussed:
            self.scheduler.add_task(self.textview_focussed.grab_focus)

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
            textview.set_editable(0)
        for buf in self.textbuffer:
            assert hasattr(buf,"handlers")
            for h in buf.handlers:
                buf.disconnect(h)

    def _connect_buffer_handlers(self):
        for textview in self.textview:
            textview.set_editable(1)
        for buf in self.textbuffer:
            id0 = buf.connect("insert-text", self.on_text_insert_text)
            id1 = buf.connect("delete-range", self.on_text_delete_range)
            id2 = buf.connect_after("insert-text", self.after_text_insert_text)
            id3 = buf.connect_after("delete-range", self.after_text_delete_range)
            id4 = buf.connect("mark-set", self.on_textbuffer_mark_set)
            buf.handlers = id0, id1, id2, id3, id4

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

    def _after_text_modified(self, buffer, startline, sizechange):
        if self.num_panes > 1:
            pane = self.textbuffer.index(buffer)
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
        return FakeTextArray(self.textbuffer, [self._filter_text, lambda x:x][raw])

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
        tab_size = self.prefs.tab_size
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
        if key == "tab_size":
            tabs = pango.TabArray(10, 0)
            for i in range(10):
                tabs.set_tab(i, pango.TAB_LEFT, i*value*self.pango_char_width)
            for i in range(3):
                self.textview[i].set_tabs(tabs)
            if sourceview_available:
                for t in self.textview:
                    t.set_tabs_width(value)
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
                        self.textbuffer[i],
                        self.bufferdata[i].filename,
                        self.prefs.use_syntax_highlighting )
        elif key == "regexes":
            self._update_regexes()
        elif key == "edit_wrap_lines":
            for t in self.textview:
                t.set_wrap_mode(self.prefs.edit_wrap_lines)
        elif key == "spaces_instead_of_tabs":
            if sourceview_available:
                for t in self.textview:
                    t.set_insert_spaces_instead_of_tabs(value)

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
        response = gtk.RESPONSE_OK
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
            response = dialog.widget.run()
            try_save = [ b.get_active() for b in buttons]
            dialog.widget.destroy()
            if response==gtk.RESPONSE_OK:
                for i in range(self.num_panes):
                    if try_save[i]:
                        if self.save_file(i) != melddoc.RESULT_OK:
                            return gtk.RESPONSE_CANCEL
        return response

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
            pane = self.textbuffer.index(buffer)
            if self.bufferdata[pane].modified != 1:
                self.undosequence.add_action( BufferModifiedAction(buffer, self) )
            self.undosequence.add_action( BufferInsertionAction(buffer, it.get_offset(), text) )
            self.undosequence.end_group()

    def on_text_delete_range(self, buffer, it0, it1):
        text = buffer.get_text(it0, it1, 0)
        pane = self.textbuffer.index(buffer)
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

    def on_open_activate(self, *args):
        pane = self._get_focused_pane()
        if pane >= 0:
            if self.bufferdata[pane].filename:
                self._open_files([self.bufferdata[pane].filename])

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
                    self.gnome_entry_search_for.child.connect("activate", self.on_entry_search_for_activate)
                    self.widget.show_all()
                def on_destroy(self, *args):
                    self.parent.find_dialog = None
                    self.widget.destroy()
                def on_entry_search_for_activate(self, *args):
                    search_text = self.gnome_entry_search_for.get_active_text()
                    self.gnome_entry_search_for.prepend_text(search_text)
                    self.parent._find_text(search_text,
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

    def popup_in_pane(self, pane):
        self.actiongroup.get_action("CopyAllLeft").set_sensitive(pane > 0)
        self.actiongroup.get_action("CopyAllRight").set_sensitive(pane+1 < self.num_panes)
        self.popup_menu.popup(None, None, None, 3, gtk.get_current_event_time())

    def on_textview_button_press_event(self, textview, event):
        if event.button == 3:
            textview.grab_focus()
            pane = self.textview.index(textview)
            self.popup_in_pane(pane)
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
        pane = self._get_focused_pane()
        if pane == -1:
            pane = 0
        buf = self.textbuffer[pane]
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
                self.textview[pane].scroll_to_mark(buf.get_insert(), 0)
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
                self.textbuffer[i].delete(*self.textbuffer[i].get_bounds())
                absfile = os.path.abspath(f)
                self.fileentry[i].set_filename(absfile)
                bold, bnew = self.bufferdata[i], MeldBufferData(absfile)
                if bold.filename == bnew.filename:
                    bnew.label = bold.label
                self.bufferdata[i] = bnew
        self.recompute_label()
        self.textview[len(files) >= 2].grab_focus()
        self.scheduler.add_task( self._set_files_internal(files).next )

    def _set_files_internal(self, files):
        yield _("[%s] Set num panes") % self.label_text
        self.set_num_panes( len(files) )
        self._disconnect_buffer_handlers()
        self.linediffer.diffs = [[],[]]
        self.queue_draw()
        try_codecs = self.prefs.text_codecs.split()
        yield _("[%s] Opening files") % self.label_text
        panetext = ["\n"] * self.num_panes
        tasks = []
        for i,f in enumerate(files):
            buf = self.textbuffer[i]
            if f:
                try:
                    task = misc.struct(filename = f,
                                       file = codecs.open(f, "rU", try_codecs[0]),
                                       buf = buf,
                                       codec = try_codecs[:],
                                       text = [],
                                       pane = i)
                    tasks.append(task)
                except (IOError, LookupError), e:
                    buf.set_text("\n")
                    misc.run_dialog(
                        "%s\n\n%s\n%s" % (
                            _("Could not read from '%s'") % f,
                            _("The error was:"),
                            str(e)),
                        parent = self)
            else:
                panetext[i] = buf.get_text(*buf.get_bounds())
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
        self.scheduler.add_task( lambda: self.next_diff(gdk.SCROLL_DOWN, jump_to_first=True), True )
        self.queue_draw()
        lenseq = [len(d) for d in self.linediffer.diffs]
        self.scheduler.add_task( self._update_highlighting( (0,lenseq[0]), (0,lenseq[1]) ).next )
        self._connect_buffer_handlers()
        if sourceview_available:
            for i in range(len(files)):
                if files[i]:
                    set_highlighting_enabled(self.textbuffer[i], files[i], self.prefs.use_syntax_highlighting)
        yield 0

    def _update_highlighting(self, range0, range1):
        for b in self.textbuffer:
            taglist = ["delete line", "conflict line", "replace line", "inline line"]
            table = b.get_tag_table()
            for tagname in taglist:
                tag = table.lookup(tagname)
                b.remove_tag(tag, b.get_start_iter(), b.get_end_iter() )
        for chunk in self.linediffer.all_changes(self._get_texts()):
            for i,c in enumerate(chunk):
                if c and c[0] == "replace":
                    bufs = self.textbuffer[1], self.textbuffer[i*2]
                    #tags = [b.get_tag_table().lookup("replace line") for b in bufs]
                    starts = [b.get_iter_at_line(l) for b,l in zip(bufs, (c[1],c[3])) ]
                    text1 = "\n".join( self._get_texts(raw=1)[1  ][c[1]:c[2]] ).encode("utf16")
                    text1 = struct.unpack("%iH"%(len(text1)/2), text1)[1:]
                    textn = "\n".join( self._get_texts(raw=1)[i*2][c[3]:c[4]] ).encode("utf16")
                    textn = struct.unpack("%iH"%(len(textn)/2), textn)[1:]

                    tags = [b.get_tag_table().lookup("inline line") for b in bufs]
                    # For very long sequences, bail rather than trying a very slow comparison
                    inline_limit = 8000 # arbitrary constant
                    if len(text1) > inline_limit and len(textn) > inline_limit:
                        ends = [b.get_iter_at_line(l) for b, l in zip(bufs, (c[2], c[4]))]
                        for i in range(2):
                            bufs[i].apply_tag(tags[i], starts[i], ends[i])
                        continue

                    matcher = difflib.SequenceMatcher(None, text1, textn)
                    #print "<<<\n%s\n---\n%s\n>>>" % (text1, textn)
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
        visible = textview.get_visible_rect()
        pane = self.textview.index(textview)
        start_line = self._pixel_to_line(pane, visible.y)
        end_line = 1+self._pixel_to_line(pane, visible.y+visible.height)

        width, height = textview.allocation.width, textview.allocation.height
        context = event.window.cairo_create()
        context.rectangle(0, 0, width, height)
        context.clip()
        context.set_line_width(1.0)

        def draw_change(change): # draw background and thin lines
            ypos0 = self._line_to_pixel(pane, change[1]) - visible.y
            context.set_source_rgb(*self.line_colors[change[0]])
            context.move_to(-0.5, ypos0 - 0.5)
            context.rel_line_to(width + 1, 0)
            context.stroke()
            if change[2] != change[1]:
                ypos1 = self._line_to_pixel(pane, change[2]) - visible.y
                context.move_to(-0.5, ypos1 + 0.5)
                context.rel_line_to(width + 1, 0)
                context.stroke()
                context.set_source_rgb(*self.fill_colors[change[0]])
                context.rectangle(0, ypos0, width, ypos1 - ypos0)
                context.fill()

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

        if textview.is_focus():
            context.set_line_width(3)
            curline = textview.get_buffer().get_iter_at_mark( textview.get_buffer().get_insert() ).get_line()
            ypos, height = self._line_to_pixel_plus_height(pane, curline)
            context.set_source_rgba(1,1,0,.25)
            context.rectangle(0,ypos-visible.y, width, height)
            context.fill()
        
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
        buf = self.textbuffer[pane]
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
        if bufdata.encoding:
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

    def make_patch(self, *extra):
        fontdesc = pango.FontDescription(self.prefs.get_current_font())
        override = {}
        if sourceview_available:
            override["GtkTextView"] = gsv.SourceView
            override["GtkTextBuffer"] = gsv.SourceBuffer
        dialog = gnomeglade.Component( paths.share_dir("glade2/filediff.glade"), "patchdialog", override)
        dialog.widget.set_transient_for( self.widget.get_toplevel() )
        texts = [b.get_text(*b.get_bounds()).split("\n") for b in self.textbuffer]
        texts[0] = [l+"\n" for l in texts[0]]
        texts[1] = [l+"\n" for l in texts[1]]
        names = [self._get_pane_label(i) for i in range(2)]
        prefix = os.path.commonprefix( names )
        names = [n[prefix.rfind("/") + 1:] for n in names]
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
        pane = self.textbuffer.index(buf)
        self.bufferdata[pane].writable = yesno
        self.recompute_label()

    def set_buffer_modified(self, buf, yesno):
        pane = self.textbuffer.index(buf)
        self.bufferdata[pane].modified = yesno
        self.recompute_label()

    def save(self, *extra):
        pane = self._get_focused_pane()
        if pane >= 0:
            self.save_file(pane)

    def save_as(self, *extra):
        pane = self._get_focused_pane()
        if pane >= 0:
            self.save_file(pane, True)

    def save_all(self):
        for i in range(self.num_panes):
            if self.bufferdata[i].modified:
                self.save_file(i)

    def on_fileentry_activate(self, entry):
        if self.on_delete_event() != gtk.RESPONSE_CANCEL:
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
        text = self.textbuffer[src_pane].get_text(*self.textbuffer[src_pane].get_bounds())
        self.on_text_begin_user_action()
        self.textbuffer[dst_pane].set_text(text)
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
        self.set_files([None] * self.num_panes)

    def queue_draw(self, junk=None):
        for i in range(self.num_panes-1):
            self.linkmap[i].queue_draw()
        for i in range(self.num_panes):
            self.scrolledwindow[i].get_vscrollbar().queue_draw()

        #
        # scrollbars
        #
    def _sync_hscroll(self, adjustment):
        if not self._sync_hscroll_lock:
            self._sync_hscroll_lock = True
            adjs = map( lambda x: x.get_hadjustment(), self.scrolledwindow)
            adjs.remove(adjustment)
            val = adjustment.get_value()
            for a in adjs:
                a.set_value(val)
            self._sync_hscroll_lock = False

    def _sync_vscroll(self, adjustment):
        # only allow one scrollbar to be here at a time
        if (self.keymask & MASK_SHIFT)==0 and not self._sync_vscroll_lock:
            self._sync_vscroll_lock = True
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
            it = self.textview[master].get_line_at_y(int(master_y))[0]
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
                it = self.textbuffer[i].get_iter_at_line(int(other_line))
                val, height = self.textview[i].get_line_yrange(it)
                val -= (adj.page_size) * syncpoint
                val += (other_line-int(other_line)) * height
                val = misc.clamp(val, 0, adj.upper - adj.page_size)
                adj.set_value( val )

                # scrollbar influence 0->1->2 or 0<-1<-2 or 0<-1->2
                if master != 1:
                    line = other_line
                    master = 1
            for lm in self.linkmap:
                if lm.window:
                    alloc = lm.get_allocation()
                    rect = gdk.Rectangle(0, 0, alloc.width, alloc.height)
                    lm.window.invalidate_rect(rect, True)
                    lm.window.process_updates(True)
            self._sync_vscroll_lock = False

        #
        # scrollbar drawing
        #
    def on_vscroll__expose_event(self, scroll, event):
        def rect(ctx, color, y0,y1, xpad=2.5):
            ctx.set_source(color)
            context.rectangle(xpad, y0, alloc.width-2*xpad, max(2, y1-y0))
            ctx.fill_preserve()
            ctx.set_source_rgba(0, 0, 0, 1.0)
            ctx.stroke()

        scrollindex = [s.get_vscrollbar() for s in self.scrolledwindow].index(scroll)
        stepper_size = scroll.style_get_property("stepper-size") + 2

        alloc = scroll.get_allocation() # find drawable area
        alloc.y += stepper_size
        alloc.height -= 2*stepper_size
        scale = float(alloc.height) / self.textbuffer[scrollindex].get_line_count()

        context = scroll.window.cairo_create() # setup cairo
        context.set_line_width(0.5)
        context.translate( alloc.x, alloc.y )
        solid_green = cairo.SolidPattern(.5, 1, .5, 0.25)
        solid_red = cairo.SolidPattern(1, .5, .5, 0.75)
        solid_blue = cairo.SolidPattern(.5, 1, 1, 0.25)
        ctab = {"conflict":solid_red,
                "insert":solid_green,
                "replace":solid_blue,
                "delete":solid_green}
        for c in self.linediffer.single_changes(scrollindex, self._get_texts()):
            assert c[0] != "equal"
            if self.prefs.ignore_blank_lines:
                self._consume_blank_lines( self._get_texts()[scrollindex][c[1]:c[2]] )
            rect(context, ctab[c[0]], scale*c[1], scale*c[2])

    def _get_line_count(self, index):
        """Return the number of lines in the buffer of textview 'text'"""
        return self.textbuffer[index].get_line_count()

    def set_num_panes(self, n):
        if n != self.num_panes and n in (1,2,3):
            self.num_panes = n
            toshow =  self.scrolledwindow[:n] + self.fileentry[:n]
            toshow += self.linkmap[:n-1]
            map( lambda x: x.show(), toshow )

            tohide =  self.statusimage + self.scrolledwindow[n:] + self.fileentry[n:]
            tohide += self.linkmap[n-1:]
            map( lambda x: x.hide(), tohide )

            for i in range(self.num_panes):
                if self.bufferdata[i].modified:
                    self.statusimage[i].show()
            self.queue_draw()
            self.recompute_label()

    def _line_to_pixel(self, pane, line ):
        it = self.textbuffer[pane].get_iter_at_line(line)
        return self.textview[pane].get_iter_location( it ).y

    def _line_to_pixel_plus_height(self, pane, line ):
        it = self.textbuffer[pane].get_iter_at_line(line)
        return self.textview[pane].get_line_yrange( it )

    def _pixel_to_line(self, pane, pixel ):
        return self.textview[pane].get_line_at_y( pixel )[0].get_line()

    def next_diff(self, direction, jump_to_first=False):
        adjs = map( lambda x: x.get_vadjustment(), self.scrolledwindow)
        curline = self._pixel_to_line( 1, int(adjs[1].value + adjs[1].page_size/2) )
        if jump_to_first:
            # curline already has some positive value due to scrollbar size
            curline = -1
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
    def on_linkmap_expose_event(self, widget, event):
        wtotal, htotal = widget.allocation.width, widget.allocation.height
        context = widget.window.cairo_create()
        context.rectangle(event.area.x, event.area.y, event.area.width, event.area.height)
        context.clip()
        context.set_line_width(1.0)

        if self.keymask & MASK_SHIFT:
            pix0 = self.pixbuf_delete
            pix1 = self.pixbuf_delete
        elif self.keymask & MASK_CTRL:
            pix0 = self.pixbuf_copy0
            pix1 = self.pixbuf_copy1
        else: # self.keymask == 0:
            pix0 = self.pixbuf_apply0
            pix1 = self.pixbuf_apply1

        which = self.linkmap.index(widget)
        pix_start = [None] * self.num_panes
        pix_start[which  ] = self.textview[which  ].get_visible_rect().y
        pix_start[which+1] = self.textview[which+1].get_visible_rect().y

        def bounds(idx):
            return [self._pixel_to_line(idx, pix_start[idx]), self._pixel_to_line(idx, pix_start[idx]+htotal)]
        visible = [None] + bounds(which) + bounds(which+1)

        # For bezier control points
        x_steps = [-0.5, (1. / 3) * wtotal, (2. / 3) * wtotal, wtotal + 0.5]

        def paint_pixbuf_at(pixbuf, x, y):
            context.translate(x, y)
            context.set_source_pixbuf(pixbuf, 0, 0)
            context.paint()
            context.identity_matrix()

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

            # f and t are short for "from" and "to"
            f0,f1 = [self._line_to_pixel(which,   l) - pix_start[which  ] for l in c[1:3] ]
            t0,t1 = [self._line_to_pixel(which+1, l) - pix_start[which+1] for l in c[3:5] ]

            if f0 == f1:
                f0 -= 1
            if t0 == t1:
                t0 -= 1

            context.move_to(x_steps[0], f0 - 0.5)
            context.curve_to(x_steps[1], f0 - 0.5,
                             x_steps[2], t0 - 0.5,
                             x_steps[3], t0 - 0.5)
            context.line_to(x_steps[3], t1 + 0.5)
            context.curve_to(x_steps[2], t1 + 0.5,
                             x_steps[1], f1 + 0.5,
                             x_steps[0], f1 + 0.5)
            context.close_path()

            context.set_source_rgb(*self.fill_colors[c[0]])
            context.fill_preserve()

            context.set_source_rgb(*self.line_colors[c[0]])
            context.stroke()

            x = wtotal-self.pixbuf_apply0.get_width()
            if c[0] in ("insert", "replace"):
                paint_pixbuf_at(pix1, x, t0)
            if c[0] in ("delete", "replace"):
                paint_pixbuf_at(pix0, 0, f0)

        # allow for scrollbar at end of textview
        mid = int(0.5 * self.textview[0].allocation.height) + 0.5
        context.set_source_rgba(0., 0., 0., 0.5)
        context.move_to(.35 * wtotal, mid)
        context.line_to(.65 * wtotal, mid)
        context.stroke()

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
            wtotal, htotal = area.allocation.width, area.allocation.height
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
                return True
            src = which + side
            dst = which + 1 - side
            adj = self.scrolledwindow[src].get_vadjustment()

            for c in self.linediffer.pair_changes(src, dst, self._get_texts()):
                if self.prefs.ignore_blank_lines:
                    c1,c2 = self._consume_blank_lines( self._get_texts()[src][c[1]:c[2]] )
                    c3,c4 = self._consume_blank_lines( self._get_texts()[dst][c[3]:c[4]] )
                    c = c[0], c[1]+c1,c[2]-c2, c[3]+c3,c[4]-c4
                    if c[1]==c[2] and c[3]==c[4]:
                        continue
                if c[0] == "insert":
                    continue
                h = self._line_to_pixel(src, c[1]) - adj.value
                if h < 0: # find first visible chunk
                    continue
                elif h > htotal: # we've gone past last visible
                    break
                elif h < event.y and event.y < h + pix_height:
                    self.mouse_chunk = ( (src,dst), (rect_x, h, pix_width, pix_height), c)
                    break
            #print self.mouse_chunk
            return True
        return False

    def on_linkmap_button_release_event(self, area, event):
        if event.button == 1:
            if self.focus_before_click:
                self.focus_before_click.grab_focus()
                self.focus_before_click = None
            if self.mouse_chunk:
                (src,dst), rect, chunk = self.mouse_chunk
                self.mouse_chunk = None
                # check we're still in button
                inrect = lambda p, r: (r[0] < p.x < r[0] + r[2]) and (r[1] < p.y < r[1] + r[3])
                if inrect(event, rect):
                    # gtk tries to jump back to where the cursor was unless we move the cursor
                    self.textview[src].place_cursor_onscreen()
                    self.textview[dst].place_cursor_onscreen()
                    chunk = chunk[1:]

                    b0 = self.textbuffer[src]
                    b1 = self.textbuffer[dst]
                    if self.keymask & MASK_SHIFT: # delete
                        b0.delete(b0.get_iter_at_line(chunk[0]), b0.get_iter_at_line(chunk[1]))
                    elif self.keymask & MASK_CTRL: # copy up or down
                        t0 = b0.get_text( b0.get_iter_at_line(chunk[0]), b0.get_iter_at_line(chunk[1]), 0)
                        if event.y - rect[1] < 0.5 * rect[3]: # copy up
                            b1.insert_with_tags_by_name(b1.get_iter_at_line(chunk[2]), t0, "edited line")
                        else: # copy down
                            b1.insert_with_tags_by_name(b1.get_iter_at_line(chunk[3]), t0, "edited line")
                    else: # replace
                        t0 = b0.get_text( b0.get_iter_at_line(chunk[0]), b0.get_iter_at_line(chunk[1]), 0)
                        self.on_text_begin_user_action()
                        b1.delete(b1.get_iter_at_line(chunk[2]), b1.get_iter_at_line(chunk[3]))
                        b1.insert_with_tags_by_name(b1.get_iter_at_line(chunk[2]), t0, "edited line")
                        self.on_text_end_user_action()
            return True
        return False

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

