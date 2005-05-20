### Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>

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
import difflib
import math
import os
import re
import sys
import tempfile

import gnomeprint
import gnomeprint.ui
import gobject
import gtk
import gtk.keysyms
import pango

import diffutil
import fileprint
import findreplace
import glade
import melddoc
import misc
import paths
import sourceview
import stock
import undo
import undoaction

class FileDiff(melddoc.MeldDoc, glade.Component):
    """Two or three way diff of text files.
    """

    UI_DEFINITION = """
    <ui>
      <menubar name="MenuBar">
        <menu action="file_menu">
          <placeholder name="file_extras">
            <separator/>
            <menuitem action="save"/>
            <menuitem action="save_as"/>
            <menuitem action="save_all"/>
            <menu action="save_menu">
              <menuitem action="save_pane0"/>
              <menuitem action="save_pane1"/>
              <menuitem action="save_pane2"/>
            </menu>
            <separator/>
            <menuitem action="print"/>
            <separator/>
            <menuitem action="close"/>
          </placeholder>
        </menu>
        <placeholder name="menu_extras">
          <menu action="edit_menu">
            <menuitem action="undo"/>
            <menuitem action="redo"/>
            <separator/>
            <menuitem action="find"/>
            <menuitem action="find_next"/>
            <menuitem action="find_replace"/>
            <separator/>
            <menuitem action="cut"/>
            <menuitem action="copy"/>
            <menuitem action="paste"/>
            <separator/>
          </menu>
          <menu action="diff_menu">
            <menuitem action="next_difference"/>
            <menuitem action="previous_difference"/>
            <separator/>
            <menuitem action="one_pane"/>
            <menuitem action="two_panes"/>
            <menuitem action="three_panes"/>
            <separator/>
            <menuitem action="replace_left_file"/>
            <menuitem action="replace_right_file"/>
            <separator/>
          </menu>
        </placeholder>
      </menubar>
      <toolbar name="ToolBar">
          <separator/>
          <toolitem action="save"/>
          <toolitem action="refresh"/>
          <separator/>
          <toolitem action="undo"/>
          <toolitem action="redo"/>
          <toolitem action="find"/>
          <toolitem action="find_replace"/>
          <separator/>
          <toolitem action="next_difference"/>
          <toolitem action="previous_difference"/>
          <separator/>
      </toolbar>
    </ui>
    """

    UI_ACTIONS = (
        # action_name, stock_icon, label, accelerator, tooltip,
        ('file_menu', None, _('_File')),
            ('save', gtk.STOCK_SAVE, _('_Save'), '<Control>s', _('Save the current file')),
            ('save_as', gtk.STOCK_SAVE_AS, _('_Save As...'), None, _('Save the current file')),
            ('save_all', gtk.STOCK_SAVE, _('_Save All'), '<Control><Shift>s', _('Save all files')),
            ('save_menu', gtk.STOCK_SAVE, _('_Save Pane')),
                ('save_pane0', gtk.STOCK_SAVE, _('Pane 1'), '<Control>1', ''),
                ('save_pane1', gtk.STOCK_SAVE, _('Pane 2'), '<Control>2', ''),
                ('save_pane2', gtk.STOCK_SAVE, _('Pane 3'), '<Control>3', ''),
            ('print', gtk.STOCK_PRINT, _('_Print...'), '<Control><Shift>p', _('Print this comparison')),
            ('close', gtk.STOCK_CLOSE, _('_Close'), '<Control>w', _('Close this tab')),
        ('edit_menu', None, _('_Edit')),
            ('refresh', gtk.STOCK_REFRESH, _('Refres_h'), None, ''),
            ('undo', gtk.STOCK_UNDO, _('_Undo'), '<Control>z', _('Undo last change')),
            ('redo', gtk.STOCK_REDO, _('_Redo'), '<Control><Shift>z', _('Redo last change')),
            ('find', gtk.STOCK_FIND, _('_Find'), '<Control>f', _('Search the document')),
            ('find_next', gtk.STOCK_FIND, _('_Find Next'), '<Control>g', _('Repeat the last find')),
            ('find_replace', gtk.STOCK_FIND_AND_REPLACE, _('_Replace'), '<Control>r', _('Find and replace text')),
            ('cut', gtk.STOCK_CUT, _('Cu_t'), '<Control>x', _('Copy selected text')),
            ('copy', gtk.STOCK_PASTE, _('_Copy'), '<Control>c', _('Copy selected text')),
            ('paste', gtk.STOCK_PASTE, _('_Paste'), '<Control>v', _('Paste selected text')),
        ('diff_menu', None, _('Diff')),
            ('next_difference', gtk.STOCK_GO_DOWN, _('_Next'), '<Control>d', _('Next difference')),
            ('previous_difference', gtk.STOCK_GO_UP, _('Pr_ev'), '<Control>e', _('Previous difference')),
            ('one_pane', None, _('One pane'), '<Control><Alt>1', '', 1, 'num_panes'),
            ('two_panes', None, _('Two panes'), '<Control><Alt>2', '', 2, 'num_panes'),
            ('three_panes', None, _('Three panes'), '<Control><Alt>3', '', 3, 'num_panes'),
            ('replace_left_file', gtk.STOCK_GO_BACK, _('Copy contents left'), None, None),
            ('replace_right_file', gtk.STOCK_GO_FORWARD, _('Copy contents right'), None, None),
    )
    MASK_SHIFT = 1
    MASK_CTRL = 2
    keylookup = { gtk.keysyms.Shift_L : MASK_SHIFT,
                  gtk.keysyms.Shift_R : MASK_SHIFT,
                  gtk.keysyms.Control_L : MASK_CTRL,
                  gtk.keysyms.Control_R : MASK_CTRL }

    class BufferExtra(object):
        __slots__ = ("writable", "__filename", "encoding", "newlines")
        def __init__(self, filename=None):
            self.writable = 1
            self.filename = filename
            self.encoding = None
            self.newlines = None
        def set_filename(self, absname):
            if absname:
                self.writable = os.access(absname, os.W_OK)
            self.__filename = absname
        filename = property(lambda x : x.__filename, set_filename)

    class ContextMenu(glade.Component):
        def __init__(self, parent):
            self.parent = parent
            self.pane = -1
            gladefile = paths.share_dir("glade2/filediff.glade")
            glade.Component.__init__(self, gladefile, "popup")
            self.connect_signal_handlers()
        def popup_in_pane( self, pane ):
            self.pane = pane
            self.copy_left.set_sensitive( pane > 0 )
            self.copy_right.set_sensitive( pane+1 < self.parent.num_panes )
            self.edit.set_sensitive(self.parent.bufferextra[self.pane].filename != None)
            self.toplevel.popup( None, None, None, 3, gtk.get_current_event_time() )
        def on_save__activate(self, menuitem):
            self.parent.save_file(self.pane)
        def on_save_as__activate(self, menuitem):
            self.parent.save_file(self.pane, 1)
        def on_cut__activate(self, menuitem):
            self.parent.action_cut__activate()
        def on_copy__activate(self, menuitem):
            self.parent.action_copy__activate()
        def on_paste__activate(self, menuitem):
            self.parent.action_paste__activate()
        def on_copy_left__activate(self, menuitem):
            self.parent.copy_entire_file(-1)
        def on_copy_right__activate(self, menuitem):
            self.parent.copy_entire_file(1)
        def on_edit__activate(self, menuitem):
            self.parent._edit_files( [self.parent.bufferextra[self.pane].filename] )

    def __init__(self, prefs, num_panes):
        """Start up an filediff with num_panes empty contents.
        """
        melddoc.MeldDoc.__init__(self, prefs.filediff)
        # text views
        override = {}
        override["GtkTextView"] = sourceview.SourceView
        override["GtkTextBuffer"] = sourceview.SourceBuffer
        glade.Component.__init__(self, paths.share_dir("glade2/filediff.glade"), "filediff", override)
        self.map_widgets_into_lists( ["textview", "filecombo", "openbutton", "diffmap", "pane", "scrolledwindow", "linkmap", "statusbutton"] )
        self.fileentry = [ glade.FileEntry(c,b) for c,b in zip(self.filecombo, self.openbutton) ]
        # text views and buffers
        self.textbuffer = [ sourceview.SourceBuffer() for i in range(3) ]
        self.bufferextra = [ self.BufferExtra() for i in range(3) ]
        for view,buffer in zip(self.textview, self.textbuffer):
            view.set_show_line_numbers( self.prefs.line_numbers )
            view.set_wrap_mode( self.prefs.wrap_lines )
            view.set_buffer(buffer)
            def add_tag(name, props):
                tag = buffer.create_tag(name)
                for p,v in props.items():
                    tag.set_property(p,v)
            common = self.prefs.common
            add_tag("inline line",   {"background": common.color_inline_bg,
                                      "foreground": common.color_inline_fg} )
        # ui and actions
        self.actiongroup = gtk.ActionGroup("FilediffActions")
        self.add_actions( self.actiongroup, self.UI_ACTIONS )
        self.map_widgets_into_lists( ["action_save_pane"] )
        # undo
        self.undosequence = undo.UndoSequence()
        self.undosequence.connect("can-undo", lambda o,can:
            self.action_undo.set_property("sensitive",can))
        self.undosequence.connect("can-redo", lambda o,can:
            self.action_redo.set_property("sensitive",can))
        self.undosequence.clear()
        # scroll bars
        for i in range(3):
            w = self.scrolledwindow[i]
            v,h = w.get_vadjustment(), w.get_hadjustment()
            v.signal_handler_ids = [v.connect("value-changed", self._sync_vscroll )]
            h.signal_handler_ids = [h.connect("value-changed", self._sync_hscroll )]
        group = gtk.SizeGroup(gtk.SIZE_GROUP_VERTICAL)
        group.add_widget(self.spacer0)
        group.add_widget(self.fileentryhbox0)
        # misc state variables
        self.popup_menu = self.ContextMenu(self)
        self.find_dialog = None
        self.last_find_replace = None
        self.keymask = 0
        self.deleted_lines_pending = -1
        self.textview_focussed = None
        self._update_regexes()
        self.load_font()
        self.differ = diffutil.Differ()
        self.num_panes = 0
        self.set_num_panes(num_panes)
        self.connect_signal_handlers()

    def on_textbuffer__mark_set(self, buf, it, mark):
        if mark.get_name() == "insert":
            self._update_cursor_status(buf)

    def _update_regexes(self):
        self.regexes = []
        for r in [ misc.ListItem(i) for i in self.prefs.common.regexes ]:
            if r.active:
                try:
                    self.regexes.append( re.compile(r.value+"(?m)") )
                except re.error, e:
                    pass

    def _update_cursor_status(self, buf):
        def update():
            iter = buf.get_iter_at_mark( buf.get_insert() )
            view = self.textview[ self.textbuffer.index(buf) ]
            status = "%s : %s" % ( _("Insert,Overwrite").split(",")[ view.get_overwrite() ], #insert/overwrite
                                   _("Line %i, Column %i") % (iter.get_line()+1, iter.get_line_offset()+1) ) #line/column
            self.emit("status-changed", status)
        self.scheduler.add_task( update )

    def on_textview__move_cursor(self, view, *args):
        self._update_cursor_status(view.get_buffer())

    def on_textview__focus_in_event(self, view, event):
        self.textview_focussed = view
        self._update_cursor_status(view.get_buffer())

    def on_filediff__focus_in_event(self, view, event):
        self.textview_focussed = view
        self._update_cursor_status(view.get_buffer())

    def on_statusbutton__clicked(self, button):
        pane = self.statusbutton.index(button)
        self.save_file(pane)

    #
    # Container methods
    #
    def on_container_delete_event(self, app_quit=0):
        modified = [b.get_modified() for b in self.textbuffer]
        if 1 in modified:
            dialog = glade.Component( paths.share_dir("glade2/filediff.glade"), "closedialog")
            dialog.toplevel.set_transient_for(self.toplevel.get_toplevel())
            buttons = []
            for i in range(self.num_panes):
                b = gtk.CheckButton( self._get_filename(i) )
                buttons.append(b)
                dialog.box.pack_start(b, 1, 1)
                if not modified[i]:
                    b.set_sensitive(-1)
                else:
                    b.set_active(1)
            dialog.toplevel.show_all()
            if not app_quit:
                dialog.button_quit.hide()
            response = dialog.toplevel.run()
            try_save = [ b.get_active() for b in buttons]
            dialog.toplevel.destroy()
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

    def on_container_switch_event(self, uimanager):
        self.ui_merge_id = uimanager.add_ui_from_string( self.UI_DEFINITION )
        uimanager.insert_action_group( self.actiongroup, -1 )
        if self.textview_focussed:
            self.scheduler.add_task( self.textview_focussed.grab_focus )

    def on_container_switch_out_event(self, uimanager):
        uimanager.remove_ui( self.ui_merge_id )
        uimanager.remove_action_group( self.actiongroup )
        uimanager.ensure_update()

    def _after_text_modified(self, buffer, startline, sizechange):
#        if self.num_panes > 1:
#            pane = self.textbuffer.index(buffer)
#            range = self.differ.change_sequence( pane, startline, sizechange, self._get_texts())
#            for iter in self._update_highlighting( range[0], range[1] ):
#                pass
#            self.queue_draw()
        self._update_cursor_status(buffer)

    def _get_texts(self, raw=0):
        class FakeTextRaw(object):
            def __init__(self, buf, regexes):
                self.buf = buf
            def __getslice__(self, lo, hi):
                b = self.buf
                return b.get_text(b.get_iter_at_line(lo), b.get_iter_at_line(hi), 0).split("\n")
        class FakeTextFiltered(object):
            def __init__(self, buf, regexes):
                self.buf, self.regexes = buf, regexes
            def __getslice__(self, lo, hi):
                b = self.buf
                #txt = b.get_text(b.get_iter_at_line(lo), b.get_iter_at_line(hi), 0)
                i1 = b.get_iter_at_line(hi)
                i1.forward_to_line_end()
                txt = b.get_text(b.get_iter_at_line(lo), i1, 0)
                for r in self.regexes:
                    txt = r.sub("", txt)
                return txt.split("\n")
        FakeText = (FakeTextFiltered,FakeTextRaw)[raw]
        class FakeTextArray(object):
            def __init__(self, bufs, regexes):
                self.texts = [FakeText(b, regexes) for b in  bufs]
            def __getitem__(self, i):
                return self.texts[i]
        return FakeTextArray( self.textbuffer, self.regexes )

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
        load = lambda x: glade.load_pixbuf( paths.share_dir("glade2/pixmaps/"+x), self.pixels_per_line)
        self.pixbuf_apply0 = load("button_apply0.xpm")
        self.pixbuf_apply1 = load("button_apply1.xpm")
        self.pixbuf_delete = load("button_delete.xpm")
        self.pixbuf_copy =   load("button_copy.xpm")

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
        elif key == "custom_font_enabled" or key == "custom_font":
            self.load_font()
        elif key == "line_numbers":
            for t in self.textview:
                t.set_show_line_numbers( value )
        elif key == "syntax_highlighting":
            for i in range(self.num_panes):
                sourceview.set_highlighting_enabled(
                    self.textbuffer[i],
                    self.bufferextra[i].filename,
                    self.prefs.syntax_highlighting )
        elif key == "regexes":
            self._update_regexes()
        elif key == "wrap_lines":
            for text in self.textview:
                text.set_wrap_mode( value )

    def on_toplevel__key_press_event(self, object, event):
        x = self.keylookup.get(event.keyval, 0)
        if self.keymask | x != self.keymask:
            self.keymask |= x
            self._update_merge_buttons()

    def on_toplevel__key_release_event(self, object, event):
        x = self.keylookup.get(event.keyval, 0)
        if self.keymask & ~x != self.keymask:
            self.keymask &= ~x
            self._update_merge_buttons()

    def is_modified(self):
        state = [b.get_modified() for b in self.textbuffer]
        return 1 in state

    def _get_filename(self, i):
        return self.bufferextra[i].filename or "<unnamed>"


        #
        # text buffer undo/redo
        #
    def on_textbuffer__begin_user_action(self, *buffer):
        self.undosequence.begin_group()

    def on_textbuffer__end_user_action(self, *buffer):
        self.undosequence.end_group()

    def on_textbuffer__modified_changed(self, buf):
        self.recompute_label()

    def on_textbuffer__insert_text(self, buffer, iter, text, textlen):
        if not self.undosequence.in_progress:
            self.undosequence.begin_group()
            if not buffer.get_modified():
                self.undosequence.add_action( undoaction.TextBufferModify(buffer) )
            self.undosequence.add_action( undoaction.TextBufferInsert(buffer, iter.get_offset(), text) )
            self.undosequence.end_group()

    def on_textbuffer__delete_range(self, buffer, iter0, iter1):
        text = buffer.get_text(iter0, iter1, 0)
        pane = self.textbuffer.index(buffer)
        assert self.deleted_lines_pending == -1
        self.deleted_lines_pending = text.count("\n")
        if not self.undosequence.in_progress:
            self.undosequence.begin_group()
            if not buffer.get_modified():
                self.undosequence.add_action( undoaction.TextBufferModify(buffer) )
            self.undosequence.add_action( undoaction.TextBufferDelete(buffer, iter0.get_offset(), text) )
            self.undosequence.end_group()

    def after_textbuffer__insert_text(self, buffer, iter, newtext, textlen):
        lines_added = newtext.count("\n")
        starting_at = iter.get_line() - lines_added
        self._after_text_modified(buffer, starting_at, lines_added)

    def after_textbuffer__delete_range(self, buffer, iter0, iter1):
        starting_at = iter0.get_line()
        assert self.deleted_lines_pending != -1
        self._after_text_modified(buffer, starting_at, -self.deleted_lines_pending)
        self.deleted_lines_pending = -1

        #
        #
        #

    def _get_focused_textview(self):
        for i in range(self.num_panes):
            t = self.textview[i]
            if t.is_focus():
                return t
        return None

    def on_textview__button_press_event(self, textview, event):
        if event.button == 3:
            textview.grab_focus()
            pane = self.textview.index(textview)
            self.popup_menu.popup_in_pane( pane )
            return 1

    def on_textview__toggle_overwrite(self, view):
        lock = self.enter_locked_region("__on_textview__toggle_overwrite")
        if lock:
            over = not view.get_overwrite()
            [v.set_overwrite(over) for v in self.textview if v != view]
            self._update_cursor_status(view.get_buffer())
            self.exit_locked_region(lock)

        #
        # text buffer loading/saving
        #

    def recompute_label(self):
        filenames = [ self._get_filename(i) for i in range(3) ]
        for i in range(self.num_panes):
            if self.bufferextra[i].writable == 0:
                self.statusbutton[i].child.set_from_stock(gtk.STOCK_SAVE_AS, gtk.ICON_SIZE_SMALL_TOOLBAR)
            else:
                self.statusbutton[i].child.set_from_stock(gtk.STOCK_SAVE, gtk.ICON_SIZE_SMALL_TOOLBAR)
            if self.textbuffer[i].get_modified() == 1:
                filenames[i] += "*"
                self.statusbutton[i].set_sensitive(True)
            else:
                self.statusbutton[i].set_sensitive(False)
        shortnames = misc.shorten_names( *filenames[:self.num_panes] )
        self.label_text = " : ".join(shortnames)
        self.emit("label-changed", self.label_text)

    def set_files(self, files):
        """Set num panes to len(files) and load each file given.
        """
        self.set_num_panes( len(files) )
        for i,f in misc.enumerate(files):
            if f:
                b = self.textbuffer[i]
                b.delete( b.get_start_iter(), b.get_end_iter() )
                absfile = os.path.abspath(f)
                self.fileentry[i].set_filename(absfile)
                self.bufferextra[i] = self.BufferExtra(absfile)
        self.recompute_label()
        self.scheduler.add_task( self._set_files_internal(files).next )

    def _set_files_internal(self, files):
        yield _("[%s] Set num panes") % self.label_text
        self.block_signal_handlers(*self.textbuffer)
        self.differ = diffutil.Differ()
        self.queue_draw()
        try_codecs = self.prefs.text_codecs.split()
        yield _("[%s] Opening files") % self.label_text
        panetext = [None] * len(files)
        tasks = []
        buffers = self.textbuffer
        for i,f in misc.enumerate(files):
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
                    glade.run_dialog(
                        _("Could not open '%s' for reading.\n\nThe error was:\n%s") % (f, str(e)),
                        parent = self.toplevel.get_toplevel())
            else:
                panetext[i] = buffers[i].get_text( *buffers[i].get_bounds() )
        yield _("[%s] Reading files") % self.label_text
        while len(tasks):
            for t in tasks[:]:
                try:
                    nextbit = t.file.read(4096)
                except ValueError, err:
                    t.codec.pop(0)
                    if len(t.codec):
                        t.file = codecs.open(t.filename, "rU", t.codec[0])
                        t.buf.delete( t.buf.get_start_iter(), t.buf.get_end_iter() )
                        t.text = []
                    else:
                        print "codec error fallback", err
                        t.buf.delete( t.buf.get_start_iter(), t.buf.get_end_iter() )
                        glade.run_dialog(
                            _("Could not read from '%s'.\n\nI tried encodings %s.") 
                            % (t.filename, try_codecs), parent = self)
                        tasks.remove(t)
                except IOError, ioerr:
                    glade.run_dialog(
                        _("Could not read from '%s'.\n\nThe error was:\n%s")
                        % (t.filename, str(ioerr)), parent = self)
                    tasks.remove(t)
                else:
                    if len(nextbit):
                        t.buf.insert( t.buf.get_end_iter(), nextbit )
                        t.text.append(nextbit)
                    else:
                        self.bufferextra[t.pane].encoding = t.codec[0]
                        if hasattr(t.file, "newlines"):
                            self.bufferextra[t.pane].newlines = t.file.newlines
                        tasks.remove(t)
                        panetext[t.pane] = "".join(t.text)
                        #if len(panetext[t.pane]) and \
                            #panetext[t.pane][-1] != "\n" and \
                            #self.prefs.supply_newline:
                                #t.buf.insert( t.buf.get_end_iter(), "\n")
                                #panetext[t.pane] += "\n"
            yield 1
        self.undosequence.clear()
        yield _("[%s] Computing differences") % self.label_text
        for r in self.regexes:
            panetext = [r.sub("",p) for p in panetext]
        lines = map(lambda x: x.split("\n"), panetext)
        step = self.differ.set_sequences_iter(*lines)
        while step.next() == None:
            yield 1
        self._update_merge_buttons()
        self.toplevel.queue_draw()
        lenseq = [len(d) for d in self.differ.diffs]
        self.scheduler.add_task( self._update_highlighting( (0,lenseq[0]), (0,lenseq[1]) ).next )
        self.unblock_signal_handlers(*self.textbuffer)
        for i in range(len(files)):
            if files[i]:
                sourceview.set_highlighting_enabled( self.textbuffer[i],
                files[i], self.prefs.syntax_highlighting )
        [b.set_modified(0) for b in self.textbuffer]
        yield 0

    def _update_merge_buttons(self):
        class ButtonManager:
            def __init__(self, area, textviews):
                self.area = area
                self.index = 0
                self.buttons = []
                self.textview = textviews
                self.extra = []
            def next(self, pixbuf, extra):
                try:
                    b = self.buttons[self.index]
                    self.extra[self.index] = extra
                except IndexError:
                    im = gtk.Image()
                    b = gtk.Button()
                    b.set_property("relief", gtk.RELIEF_NONE)
                    b.set_focus_on_click(False)
                    b.add(im)
                    b.show_all()
                    b.set_border_width(0)
                    self.area.put( b, 0, 0 )
                    self.buttons.append(b)
                    self.extra.append(extra)
                    b.connect("clicked", self.on_clicked)
                self.index += 1
                b.child.set_from_pixbuf(pixbuf)
                b.show()
                return b
            def on_clicked(self, button):
                operation, chunk, linkindex, side = self.extra[ self.buttons.index(button) ]
                src = linkindex + side
                dst = linkindex + (1-side)
                self.textview[src].place_cursor_onscreen()
                self.textview[dst].place_cursor_onscreen()
                off = side*2
                if operation == "delete":
                    b = self.textview[src].get_buffer()
                    b.delete(b.get_iter_at_line(chunk[1+off]), b.get_iter_at_line(chunk[2+off]))
                elif operation == "copy":
                    b0, b1 = self.textview[src].get_buffer(), self.textview[dst].get_buffer()
                    t0 = b0.get_text( b0.get_iter_at_line(chunk[1+off]), b0.get_iter_at_line(chunk[2+off]), 0)
                    b1.insert(b1.get_iter_at_line(chunk[4-off]), t0)
                else: # replace
                    b0, b1 = self.textview[src].get_buffer(), self.textview[dst].get_buffer()
                    t0 = b0.get_text( b0.get_iter_at_line(chunk[1+off]), b0.get_iter_at_line(chunk[2+off]), 0)
                    b1.begin_user_action()
                    b1.delete(b1.get_iter_at_line(chunk[3-off]), b1.get_iter_at_line(chunk[4-off]))
                    b1.insert(b1.get_iter_at_line(chunk[3-off]), t0)
                    b1.end_user_action()
            def put_back(self, button):
                self.index -= 1
            def finished(self):
                for b in self.buttons[self.index:]:
                    b.hide()
                self.index = 0
        if not hasattr(self,"_button_manager"):
            self._button_manager = [ ButtonManager(l, self.textview) for l in self.linkmap]


        if self.keymask & self.MASK_SHIFT: # delete
            operation = "delete"
            pixbufs = self.pixbuf_delete, self.pixbuf_delete
        elif self.keymask & self.MASK_CTRL: # copy up
            operation = "copy"
            pixbufs = self.pixbuf_copy, self.pixbuf_copy
        else:
            operation = "apply"
            pixbufs = self.pixbuf_apply0, self.pixbuf_apply1

        visible = [t.get_visible_rect() for t in self.textview]
        for linkindex in range(self.num_panes-1):
            start = [self._pixel_to_line(linkindex+i, visible[linkindex+i].y) for i in range(2)]
            end =   [self._pixel_to_line(linkindex+i, visible[linkindex+i].y+visible[linkindex+i].height) for i in range(2)]
            button_indent = 5
            button = self._button_manager[linkindex].next(pixbufs[0], None)
            xpos = (-button_indent, self.linkmap0.size_request()[0] - (button.size_request()[0]-button_indent))
            self._button_manager[linkindex].put_back(button)
            for change in self.differ.single_changes(linkindex*2, linkindex==1):
                if change[2] < start[0] and change[4] < start[1]: continue
                if change[1] > end[0] and change[3] > end[1]: break
                for side in range(2):
                    if change[0] == ("insert","delete")[side] and self.keymask:
                        continue
                    button = self._button_manager[linkindex].next( pixbufs[side], (operation, change, linkindex, side) )
                    ypos = self._line_to_pixel(linkindex+side, change[1+2*side]) - visible[linkindex+side].y
                    if change[0] == ("insert","delete")[side]:
                        ypos -= button.size_request()[1]/2
                    self.linkmap[linkindex].move( button, xpos[side], ypos)
            self._button_manager[linkindex].finished()

    def _update_highlighting(self, range0, range1):
        buffers = self.textbuffer
        for b in buffers:
            tag = b.get_tag_table().lookup("inline line")
            b.remove_tag(tag, b.get_start_iter(), b.get_end_iter() )

        def get_iters(buf, line0, line1):
            i0 = buf.get_iter_at_line(line0)
            i1 = buf.get_iter_at_line(line1-1)
            if not i1.ends_line(): i1.forward_to_line_end()
            return i0,i1

        for i,diff in enumerate(self.differ.diffs):
            for c in diff:
                if c[0] == "replace":
                    bufs = buffers[1], buffers[i*2]
                    tags = [b.get_tag_table().lookup("replace line") for b in bufs]
                    starts = [b.get_iter_at_line(l) for b,l in zip(bufs, (c[1],c[3])) ]
#                    for b, t, s, l in zip(bufs, tags, starts, (c[2],c[4])):
#                        b.apply_tag(t, s, b.get_iter_at_line(l))
                    if 0:
                        text1 = "\n".join( self._get_texts(raw=1)[1  ][c[1]:c[2]] )
                        textn = "\n".join( self._get_texts(raw=1)[i*2][c[3]:c[4]] )
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
            yield 1
            #if chunk[0] and chunk[0][0] == "conflict":
            #    chunk0, chunk1 = chunk
            #    ranges = chunk0[3:5], chunk0[1:3], chunk1[3:5]
            #    starts = [b.get_iter_at_line(l[0]) for b,l in zip(buffers, ranges) ]
            #    texts = [ "\n".join( self._get_texts(raw=1)[i].__getslice__(*ranges[i]) ) for i in range(3) ]
            #    tags = [b.get_tag_table().lookup("inline line2") for b in buffers]
            #    differ = diffutil.Differ(*texts)
            #    for change in differ.all_changes(texts):
            #        print change
            #        for i,c in enumerate(change):
            #            if c and i==0:
            #                print c
            #                s,e = starts[i].copy(), starts[i].copy()
            #                s.forward_chars( c[3] )
            #                e.forward_chars( c[4] )
            #                buffers[i].apply_tag(tags[i], s, e)
        
    def save_file(self, pane, saveas=0):
        buf = self.textbuffer[pane]
        bufdata = self.bufferextra[pane]
        if saveas or not bufdata.filename or bufdata.writable == 0:
            fselect = gtk.FileSelection( _("Save buffer %i as.") % (pane+1))
            fselect.set_has_separator(False)
            fselect.set_transient_for(self.toplevel.get_toplevel() )
            response = fselect.run()
            if response != gtk.RESPONSE_OK:
                fselect.destroy()
                return melddoc.RESULT_ERROR
            else:
                filename = fselect.get_filename()
                fselect.destroy()
                if os.path.exists(filename):
                    response = glade.run_dialog(
                        _('"%s" exists!\nOverwrite?') % os.path.basename(filename),
                        parent = self,
                        buttonstype = gtk.BUTTONS_YES_NO)
                    if response == gtk.RESPONSE_NO:
                        return melddoc.RESULT_ERROR
                bufdata.filename = os.path.abspath(filename)
                self.fileentry[pane].set_filename( bufdata.filename )
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), 0)
        if bufdata.newlines:
            if type(bufdata.newlines) == type(""):
                if(bufdata.newlines) != '\n':
                    text = text.replace("\n", bufdata.newlines)
            elif type(bufdata.newlines) == type(()):
                buttons = {'\n':("UNIX (LF)",0), '\r\n':("DOS (CR-LF)", 1), '\r':("MAC (CR)",2) }
                newline = glade.run_dialog( _("This file '%s' contains a mixture of line endings.\n\nWhich format would you like to use?") % bufdata.filename,
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
            text = text.encode(bufdata.encoding)
        try:
            open(bufdata.filename, "w").write(text)
        except IOError, e:
            glade.run_dialog(
                maintext = _("Error writing to %s\n\n%s.") % (bufdata.filename, e),
                parent = self.toplevel.get_toplevel(),
                messagetype = gtk.MESSAGE_ERROR,
                buttonstype = gtk.BUTTONS_OK)
            return melddoc.RESULT_ERROR
        else:
            self.emit("file-changed", bufdata.filename)
            self.undosequence.clear()
            buf.set_modified(False)
        return melddoc.RESULT_OK

    def on_fileentry__activate(self, entry):
        if self.on_container_delete_event() == gtk.RESPONSE_OK:
            files = [ e.get_filename() for e in self.fileentry[:self.num_panes] ]
            self.set_files(files)
        return 1

    def _get_focused_pane(self):
        for i,t in enumerate(self.textview):
            if t.is_focus():
                return i
        return -1

    def copy_entire_file(self, direction):
        assert direction in (-1,1)
        src_pane = self._get_focused_pane()
        dst_pane = src_pane + direction
        assert dst_pane in range(self.num_panes)
        buffers = self.textbuffer
        text = buffers[src_pane].get_text( buffers[src_pane].get_start_iter(), buffers[src_pane].get_end_iter() )
        self.on_textbuffer__begin_user_action()
        buffers[dst_pane].set_text( text )
        self.on_textbuffer__end_user_action()
        self.scheduler.add_task( lambda : self._sync_vscroll( self.scrolledwindow[src_pane].get_vadjustment() ) and None )

        #
        # refresh
        #
    def refresh(self, junk=None):
        modified = [b.filename for b in self.bufferextra if b.modified]
        if len(modified):
            message = _("Refreshing will discard changes in:\n%s\n\nYou cannot undo this operation.") % "\n".join(modified)
            response = glade.run_dialog( message, parent=self, messagetype=gtk.MESSAGE_WARNING, buttonstype=gtk.BUTTONS_OK_CANCEL)
            if response != gtk.RESPONSE_OK:
                return
        files = [b.filename for b in self.bufferextra[:self.num_panes] ]
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
            master = adjs.index(adjustment)
            adjs.remove(adjustment)
            val = adjustment.get_value()
            for a in adjs:
                a.set_value(val)
            self._sync_hscroll_lock = 0

    def _handlers_block(self, wid):
        for sig in wid.signal_handler_ids:
            wid.handler_block( sig )
    def _handlers_unblock(self, wid):
        for sig in wid.signal_handler_ids:
            wid.handler_unblock( sig )

    def _sync_vscroll(self, adjustment):
        [self._handlers_block(w.get_vadjustment()) for w in self.scrolledwindow]
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
        line  = (adjustment.value + adjustment.page_size * syncpoint)
        line *= self._get_line_count(master)
        line /= (adjustment.upper - adjustment.lower)

        for (i,adj) in others:
            mbegin,mend, obegin,oend = 0, self._get_line_count(master), 0, self._get_line_count(i)
            # look for the chunk containing 'line'
            for c in self.differ.single_changes(master):
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
            val = adj.lower + (other_line / self._get_line_count(i) * (adj.upper - adj.lower)) - adj.page_size * syncpoint
            val = misc.clamp(val, 0, adj.upper - adj.page_size)
            adj.set_value( val )

            # scrollbar influence 0->1->2 or 0<-1<-2 or 0<-1->2
            if master != 1:
                line = other_line
                master = 1
        self.linkmap0.queue_draw()
        self.linkmap1.queue_draw()
        self._update_merge_buttons()
        self.flushevents()
        [self._handlers_unblock(w.get_vadjustment()) for w in self.scrolledwindow]


        #
        # diffmap drawing
        #
    def on_diffmap__expose_event(self, area, event):
        diffmapindex = self.diffmap.index(area)
        textindex = (0, self.num_panes-1)[diffmapindex]
        size_of_arrow = 14 # TODO from style
        hperline = float( self.textview[textindex].get_allocation().height - 2*size_of_arrow) / self._get_line_count(textindex)
        if hperline > self.pixels_per_line:
            hperline = self.pixels_per_line
        
        yoffset = self.textview[textindex].get_allocation().y - area.get_allocation().y + size_of_arrow
        scaleit = lambda x,s=hperline,o=yoffset: x*s+o
        madj = self.scrolledwindow[textindex].get_vadjustment()

        window = area.window
        gctext = area.get_style().text_gc[0]

        rect_indent = 4
        rect_width = area.get_allocation().width - 2*rect_indent
        gc = lambda x : getattr(self.graphics_contexts, x)
        for c in self.differ.single_changes(textindex):
            assert c[0] != "equal"
            s,e = [int(x) for x in ( math.floor(scaleit(c[1])), math.ceil(scaleit(c[2]+(c[1]==c[2]))) ) ]
            window.draw_rectangle( gc(c[0]), 1, rect_indent, s, rect_width, e-s)
            window.draw_rectangle( gctext, 0, rect_indent, s, rect_width, e-s)

    def on_diffmap__motion_notify_event(self, area, event):
        self.diffmap_mouse_down(area,event)

    def on_diffmap__button_press_event(self, area, event):
        if event.button == 1:
            self.diffmap_mouse_down(area, event)
            return 1

    def diffmap_mouse_down(self, area, event):
        size_of_arrow = 14
        diffmapindex = self.diffmap.index(area)
        index = (0, self.num_panes-1)[diffmapindex]
        height = area.get_allocation().height
        fraction = (event.y - size_of_arrow) / (height - 3.75*size_of_arrow)
        adj = self.scrolledwindow[index].get_vadjustment()
        val = fraction * adj.upper - adj.page_size/2
        upper = adj.upper - adj.page_size
        adj.set_value( max( min(upper, val), 0) )

    def _get_line_count(self, index):
        """Return the number of lines in the buffer of textview 'text'"""
        return self.textbuffer[index].get_line_count()

    def set_num_panes(self, num_panes):
        if num_panes != self.num_panes and num_panes in (1,2,3):
            self.num_panes = num_panes
            for i in range(self.num_panes):
                self.pane[i].show()
                self.action_save_pane[i].set_sensitive(True)
            for i in range(self.num_panes,3):
                self.pane[i].hide()
                self.action_save_pane[i].set_sensitive(False)
            if num_panes == 1:
                [x.hide() for x in self.diffmap + self.linkmap]
                self.action_one_pane.activate()
            elif num_panes == 2:
                [x.show() for x in self.diffmap + self.linkmap[:1] ]
                self.linkmap[1].hide()
                self.action_two_panes.activate()
            elif num_panes == 3:
                [x.show() for x in self.diffmap + self.linkmap]
                self.action_three_panes.activate()
            self.scrolledwindow[0].set_placement( (gtk.CORNER_TOP_RIGHT, gtk.CORNER_TOP_LEFT)[num_panes==1] )
            self.queue_draw()
            self.set_files([None]*num_panes)

    def _line_to_pixel(self, pane, line ):
        iter = self.textbuffer[pane].get_iter_at_line(line)
        return self.textview[pane].get_iter_location( iter ).y

    def _pixel_to_line(self, pane, pixel ):
        return self.textview[pane].get_line_at_y( pixel )[0].get_line()
        
    def next_diff(self, direction):
        adjs = map( lambda x: x.get_vadjustment(), self.scrolledwindow)
        curline = self._pixel_to_line( 1, int(adjs[1].value + adjs[1].page_size/2) )
        c = None
        if direction == gtk.gdk.SCROLL_DOWN:
            for c in self.differ.single_changes(1):
                assert c[0] != "equal"
                if c[1] > curline + 1:
                    break
        else: #direction == gtk.SCROLL_STEP_BACKWARD
            for chunk in self.differ.single_changes(1):
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
            view = self._get_focused_textview()
            if view:
                buf = view.get_buffer()
                it = buf.get_iter_at_line( (c[1],c[3])[self.textview.index(view)==0] )
                buf.place_cursor( it )
            want = 0.5 * ( self._line_to_pixel(aidx, l0) + self._line_to_pixel(aidx,l1) - a.page_size )
            want = misc.clamp(want, 0, a.upper-a.page_size)
            a.set_value( want )

    def on_toplevel__realize(self, toplevel):
        window = self.toplevel.window
        gcd = window.new_gc()
        common = self.prefs.common
        gcd.set_rgb_fg_color( gtk.gdk.color_parse(common.color_delete_bg) )
        gcc = window.new_gc()
        gcc.set_rgb_fg_color( gtk.gdk.color_parse(common.color_replace_bg) )
        gce = window.new_gc()
        gce.set_rgb_fg_color( gtk.gdk.color_parse(common.color_edited_bg) )
        gcx = window.new_gc()
        gcx.set_rgb_fg_color( gtk.gdk.color_parse(common.color_conflict_bg) )
        self.graphics_contexts = misc.struct(delete=gcd, insert=gcd, replace=gcc, conflict=gcx)

    def on_textview__expose_event(self, textview, event):
        if self.num_panes == 1:
            return
        if event.window != textview.get_window(gtk.TEXT_WINDOW_TEXT) \
            and event.window != textview.get_window(gtk.TEXT_WINDOW_LEFT):
            return
        gctext = textview.get_style().text_gc[0]
        visible = textview.get_visible_rect()
        pane = self.textview.index(textview)
        start_line = self._pixel_to_line(pane, visible.y)
        end_line = self._pixel_to_line(pane, visible.y+visible.height)

        # draw background and thin lines
        gc = lambda x : getattr(self.graphics_contexts, x)
        for change in self.differ.single_changes(pane):
            if change[2] < start_line: continue
            if change[1] > end_line: break
            ypos0 = self._line_to_pixel(pane, change[1]) - visible.y
            event.window.draw_line(gctext, 0,ypos0-1, 1000,ypos0-1)
            if change[2] != change[1]:
                ypos1 = self._line_to_pixel(pane, change[2]) - visible.y
                event.window.draw_line(gctext, 0,ypos1, 1000,ypos1)
                event.window.draw_rectangle(gc(change[0]), 1, 0,ypos0, 1000,ypos1-ypos0)

        # maybe draw heavier lines for current difference
        if 0:
            view = self._get_focused_textview()
            if view and self.textview.index(view) == 0 and textview == view:
                buf = view.get_buffer()
                iter = buf.get_iter_at_mark( buf.get_insert() )
                line = iter.get_line()
                off = (0,2)[ view == textview ]
                for c in self.differ.diffs[0]:
                    if c[off+2] < line-1: continue
                    if c[off+1] > line+1: break
                    off = (2,0)[ self.textview.index(textview) ]
                    ypos0 = self._line_to_pixel(0, c[off+1]) - visible.y
                    ypos1 = self._line_to_pixel(0, c[off+2]) - visible.y
                    window.draw_rectangle(gctext, 1, 0,ypos0, 10,ypos1)
                    break

        #
        # linkmap drawing
        #
    def on_linkmap__expose_event(self, area, event):
        # not mapped? 
        if not area.window: return
        window = area.bin_window
        gctext = area.get_style().text_gc[0]
        window.clear()

        alloc = area.get_allocation()
        (wtotal,htotal) = alloc.width, alloc.height

        # gain function for smoothing
        #TODO cache these values
        bias = lambda x,g: math.pow(x, math.log(g) / math.log(0.5))
        def gain(t,g):
            if t<0.5:
                return bias(2*t,1-g)/2.0
            else:
                return (2-bias(2-2*t,1-g))/2.0
        f = lambda x: gain( x, 0.95)

        which = self.linkmap.index(area)
        pix_start = [None] * self.num_panes
        pix_start[which  ] = self.textview[which  ].get_visible_rect().y - 0
        pix_start[which+1] = self.textview[which+1].get_visible_rect().y - 0

        def bounds(idx):
            return [self._pixel_to_line(idx, pix_start[idx]), self._pixel_to_line(idx, pix_start[idx]+htotal)]
        visible = [None] + bounds(which) + bounds(which+1)

        def consume_blank_lines(txt):
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

        gc = lambda x : getattr(self.graphics_contexts, x)

        for c in self.differ.single_changes(which*2, which==1):
            if self.prefs.ignore_blank_lines:
                c1,c2 = consume_blank_lines( self._get_texts()[which  ][c[1]:c[2]] )
                c3,c4 = consume_blank_lines( self._get_texts()[which+1][c[3]:c[4]] )
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

            n = 20
            points0 = []
            points1 = []
            for t in map(lambda x: float(x)/n, range(n+1)):
                points0.append( (int(    t*wtotal), 0+int((1-f(t))*f0 + f(t)*t0 )) )
                points1.append( (int((1-t)*wtotal), 1+int(f(t)*f1 + (1-f(t))*t1 )) )

            points = points0 + points1 + [points0[0]]
            window.draw_polygon( gc(c[0]), 1, points)
            window.draw_lines(gctext, points0)
            window.draw_lines(gctext, points1)

    def on_linkmap__scroll_event(self, area, event):
        self.next_diff(event.direction)

    def action_save__activate(self, action):
        pane = self._get_focused_pane()
        if pane >= 0:
            self.save_file(pane)

    def action_save_as__activate(self, action):
        pane = self._get_focused_pane()
        if pane >= 0:
            self.save_file(pane, saveas=1)

    def action_save_all__activate(self, action):
        for i in range(self.num_panes):
            if self.textbuffer[i].get_modified():
                self.save_file(i)

    def action_save_pane0__activate(self, action):
        self.save_file(0)
    def action_save_pane1__activate(self, action):
        self.save_file(1)
    def action_save_pane2__activate(self, action):
        self.save_file(2)

    def action_print__activate(self, action):
        config = gnomeprint.config_default()
        config.set( gnomeprint.KEY_DOCUMENT_NAME, self.label_text )
        job = gnomeprint.Job(config)
        dialog = gnomeprint.ui.Dialog(job, _("Print... %s") % self.label_text,
            gnomeprint.ui.DIALOG_RANGE| gnomeprint.ui.DIALOG_COPIES)
        flags = (gnomeprint.ui.RANGE_ALL
                |gnomeprint.ui.RANGE_RANGE )
        dialog.construct_range_page(flags, 1,100, _("_Current"), _("_Range"))
        dialog.connect("response", self.on_print_dialog_response, job)
        dialog.show()

    def on_print_dialog_response(self, dialog, response, job):
        if response == gnomeprint.ui.DIALOG_RESPONSE_PREVIEW:
            self.print_show_preview(dialog)
        elif response == gnomeprint.ui.DIALOG_RESPONSE_CANCEL:
            dialog.destroy()
        elif response == gnomeprint.ui.DIALOG_RESPONSE_PRINT:
            self.print_to_job(job)
            pc = gnomeprint.Context(dialog.get_config())
            job.render(pc)
            pc.close()
            dialog.destroy()

    def print_show_preview(self, dialog):
        job = gnomeprint.Job(dialog.get_config())
        self.print_to_job(job)
        def popup():
            w = gnomeprint.ui.JobPreview(job, _("Print Preview") )
            w.set_property('allow-grow', 1)
            w.set_property('allow-shrink', 1)
            w.set_transient_for(dialog)
            w.show_all()
        self.scheduler.add_task( popup )

    def print_to_job(self, job):
        texts = [b.get_text(*b.get_bounds()).split("\n") for b in self.textbuffer]
        chunks = self.differ.all_changes(texts)
        self.scheduler.add_task( fileprint.do_print(
            job,
            texts[:self.num_panes],
            chunks, self.label_text).next )

    def action_close__activate(self, action):
        self.emit("closed")

    def action_refresh__activate(self, *action):
        self.set_files([None]*self.num_panes)

    def action_undo__activate(self, *action):
        self.undosequence.undo()

    def action_redo__activate(self, *action):
        self.undosequence.redo()

    def create_find_dialog(self):
        self.find_dialog = findreplace.FindReplaceDialog(self.toplevel.get_toplevel())
        def on_find_response(dialog, id):
            if id < 0:
                if id == gtk.RESPONSE_CLOSE:
                    self.find_dialog.toplevel.destroy()
                self.find_dialog = None
        self.find_dialog.toplevel.connect("response", on_find_response)
        self.find_dialog.connect("activate", self._do_find_replace)

    def _do_find_replace(self, dialog, state):
        view = self._get_focused_textview() or self.textview0
        if findreplace.find_replace( state, view.get_buffer() ) == False:
            glade.run_dialog(
                _("'%s' was not found.") % state.tofind,
                self.toplevel.get_toplevel(),
                messagetype=gtk.MESSAGE_INFO)
        self.last_find_replace = state

    def action_find__activate(self, *action):
        if self.find_dialog:
            self.find_dialog.toplevel.present()
        else:
            self.create_find_dialog()

    def action_find_next__activate(self, action):
        if self.last_find_replace:
            self.last_find_replace.toreplace = None
            self._do_find_replace(None, self.last_find_replace )
        else:
            self.action_find__activate()

    def action_find_replace__activate(self, *action):
        if self.find_dialog:
            self.find_dialog.enable_search_replace()
            self.find_dialog.toplevel.present()
        else:
            self.create_find_dialog()
            self.find_dialog.enable_search_replace()

    def action_next_difference__activate(self, action):
        self.next_diff(gtk.gdk.SCROLL_DOWN)

    def action_previous_difference__activate(self, action):
        self.next_diff(gtk.gdk.SCROLL_UP)

    def action_num_panes__changed(self, group, action):
        self.set_num_panes( action.get_property("value") )

    def action_replace_left_file__activate(self, action):
        self.copy_entire_file(-1)

    def action_replace_right_file__activate(self, action):
        self.copy_entire_file(+1)

    def action_cut__activate(self, *extra):
        t = self._get_focused_textview()
        if t:
            t.emit("cut-clipboard") #XXX get_buffer().cut_clipboard()

    def action_copy__activate(self, *extra):
        t = self._get_focused_textview()
        if t:
            t.emit("copy-clipboard") #XXX .get_buffer().copy_clipboard()

    def action_paste__activate(self, *extra):
        t = self._get_focused_textview()
        if t:
            t.emit("paste-clipboard") #XXX t.get_buffer().paste_clipboard(None, 1)

gobject.type_register(FileDiff)

