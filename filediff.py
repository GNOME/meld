## python

from __future__ import generators

import codecs
import math
import os
import pango
import sys
import tempfile

import gnome
import gobject
import gtk

import diffutil
import gnomeglade
import misc
import undo

gdk = gtk.gdk

################################################################################
#
# Local Functions
#
################################################################################
def _ensure_fresh_tag_exists(name, buffer, properties):
    """Tag exists in buffer and is not applied to any text"""
    table = buffer.get_tag_table()
    tag = table.lookup(name)
    if not tag:
        tag = buffer.create_tag(name)
        for prop,val in properties.items():
            tag.set_property(prop, val)
    else:
        buffer.remove_tag(tag, buffer.get_start_iter(), buffer.get_end_iter())
    return tag

################################################################################
#
# BufferInsertionAction 
#
################################################################################
class BufferInsertionAction:
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
class BufferDeletionAction:
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
class BufferModifiedAction:
    """A helper set modified flag on a text buffer"""
    def __init__(self, buffer, app):
        self.buffer, self.app = buffer, app
        self.app.set_buffer_modified(self.buffer, 1)
    def undo(self):
        self.app.set_buffer_modified(self.buffer, 0)
    def redo(self):
        self.app.set_buffer_modified(self.buffer, 1)

################################################################################
#
# FileDiff
#
################################################################################

MASK_SHIFT, MASK_CTRL, MASK_ALT = 1, 2, 3

class FileDiff(gnomeglade.Component):
    """Two or three way diff of text files"""

    __gsignals__ = {
        'label-changed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_STRING,)),
        'working-hard': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_INT,))
    }

    keylookup = {65505 : MASK_SHIFT, 65507 : MASK_CTRL, 65513: MASK_ALT}

    def __init__(self, num_panes, statusbar, prefs):
        """Start up an filediff with num_panes empty contents"""
        gnomeglade.Component.__init__(self, misc.appdir("glade2/filediff.glade"), "filediff")
        self._map_widgets_into_lists( ["textview", "fileentry", "diffmap", "scrolledwindow", "linkmap", "statusimage"] )
        self.statusbar = statusbar
        self.undosequence = undo.UndoSequence()
        self.undosequence_busy = 0
        self.keymask = 0
        self.prefs = prefs
        self.prefs.notify_add(self.on_preference_changed)
        self.load_font()
        self.deleted_lines_pending = -1

        for i in range(3):
            w = self.scrolledwindow[i]
            w.get_vadjustment().connect("value-changed", self._sync_vscroll )
            w.get_hadjustment().connect("value-changed", self._sync_hscroll )
        self._connect_buffer_handlers()

        self.linediffer = diffutil.Differ()
        load = lambda x: gnomeglade.load_pixbuf(misc.appdir("glade2/pixmaps/"+x), self.pixels_per_line)
        self.pixbuf_apply0 = load("button_apply0.xpm")
        self.pixbuf_apply1 = load("button_apply1.xpm")
        self.pixbuf_delete = load("button_delete.xpm")
        self.pixbuf_copy0  = load("button_copy0.xpm")
        self.pixbuf_copy1  = load("button_copy1.xpm")

        for l in self.linkmap: # glade bug workaround
            l.set_events(gdk.BUTTON_PRESS_MASK | gdk.BUTTON_RELEASE_MASK)

        self.num_panes = 0
        self.set_num_panes(num_panes)
        for t in self.textview:
            _ensure_fresh_tag_exists("edited line", t.get_buffer(), {"background": self.prefs.color_edited} )

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

    def _after_text_modified(self, buffer, startline, sizechange):
        buffers = [t.get_buffer() for t in self.textview[:self.num_panes] ]
        pane = buffers.index(buffer)
        def getlines(pane,lo,hi):
            b = buffers[pane]
            text = b.get_text(b.get_iter_at_line(lo), b.get_iter_at_line(hi), 0)
            lines = text.split("\n")
            if len(text) and text[-1]=='\n':
                del lines[-1]
            return lines
        self.linediffer.change_sequence( pane, startline, sizechange, getlines )
        self.refresh()

    def after_text_insert_text(self, buffer, iter, newtext, textlen):
        lines_added = newtext.count("\n")
        starting_at = iter.get_line() - lines_added
        self._after_text_modified(buffer, starting_at, lines_added)

    def after_text_delete_range(self, buffer, iter0, iter1):
        starting_at = iter0.get_line()
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
        elif 0:
            self.statusbar.add_status("Setting '%s' to '%s' default encoding" % (key,value) )

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
        state = map(lambda x: x.get_buffer().get_data("modified"), self.textview)
        return 1 in state

    def on_delete_event(self, parent):
        state = map(lambda x: x.get_buffer().get_data("modified"), self.textview)
        delete = gnomeglade.DELETE_OK
        if 1 in state:
            dialog = gnomeglade.Dialog(misc.appdir("glade2/filediff.glade"), "closedialog")
            dialog.widget.set_transient_for(self.widget.get_toplevel())
            buttons = []
            for i in range(self.num_panes):
                b = gtk.ToggleButton( self.fileentry[i].get_full_path(0) or "<unnamed>" )
                buttons.append(b)
                dialog.box.pack_start(b)
                if state[i]==0:
                    b.set_sensitive(0)
            dialog.widget.show_all()
            response = dialog.widget.run()
            try_save = [ b.get_active() for b in buttons]
            #print "try_save", try_save
            dialog.widget.destroy()
            if response==gtk.RESPONSE_OK:
                for i in range(self.num_panes):
                    if try_save[i]:
                        if self.save_file(i) != gnomeglade.RESULT_OK:
                            delete = gnomeglade.DELETE_ABORT
            else:
                delete = gnomeglade.DELETE_ABORT
        return delete

        #
        # text buffer undo/redo
        #
    def on_text_begin_user_action(self, *buffer):
        self.undosequence.begin_group()

    def on_text_end_user_action(self, *buffer):
        self.undosequence.end_group()

    def on_text_insert_text(self, buffer, iter, text, textlen):
        if not self.undosequence_busy:
            self.undosequence.begin_group()
            if buffer.get_data("modified") != 1:
                self.undosequence.add_action( BufferModifiedAction(buffer, self) )
            self.undosequence.add_action( BufferInsertionAction(buffer, iter.get_offset(), text) )
            self.undosequence.end_group()

    def on_text_delete_range(self, buffer, iter0, iter1):
        text = buffer.get_text(iter0, iter1, 0)
        pane = self.textview.index(buffer.textview)
        assert self.deleted_lines_pending == -1
        self.deleted_lines_pending = text.count("\n")
        if not self.undosequence_busy:
            self.undosequence.begin_group()
            if buffer.get_data("modified") != 1:
                self.undosequence.add_action( BufferModifiedAction(buffer, self) )
            self.undosequence.add_action( BufferDeletionAction(buffer, iter0.get_offset(), text) )
            self.undosequence.end_group()

    def undo(self):
        if self.undosequence.can_undo():
            self.undosequence_busy = 1
            try:
                self.undosequence.undo()
            finally:
                self.undosequence_busy = 0

    def redo(self):
        if self.undosequence.can_redo():
            self.undosequence_busy = 1
            try:
                self.undosequence.redo()
            finally:
                self.undosequence_busy = 0
            self.undosequence_busy = 0

        #
        # text buffer loading/saving
        #
    def _set_text(self, text, filename, pane, writable=1):
        """Set the contents of 'pane' to utf8 'text'"""
        self.fileentry[pane].set_filename(filename)
        buffer = self.textview[pane].get_buffer()
        if self.prefs.supply_newline and (len(text)==0 or text[-1] != '\n'):
            text += "\n"
        buffer.set_text( text )
        _ensure_fresh_tag_exists("edited line", buffer, {"background": self.prefs.color_edited} )
        self.set_buffer_modified(buffer, 0)
        self.set_buffer_writable(buffer, writable)

    def label_changed(self):
        filenames = []
        for i in range(self.num_panes):
            f = self.fileentry[i].get_full_path(0) or ""
            filenames.append( f )
        shortnames = misc.shorten_names(*filenames)
        for i in range(self.num_panes):
            if self.textview[i].get_buffer().get_data("modified") == 1:
                shortnames[i] += "*"
                self.statusimage[i].show()
                self.statusimage[i].set_from_stock(gtk.STOCK_SAVE, gtk.ICON_SIZE_SMALL_TOOLBAR)
            elif self.textview[i].get_buffer().get_data("writable") == 0:
                self.statusimage[i].show()
                self.statusimage[i].set_from_stock(gtk.STOCK_MISSING_IMAGE, gtk.ICON_SIZE_SMALL_TOOLBAR)
            else:
                self.statusimage[i].hide()
        labeltext = " : ".join(shortnames) + " "
        self.emit("label-changed", labeltext)

    def _dialog(self, text, type=gtk.MESSAGE_WARNING):
        d = gtk.MessageDialog(None,
                gtk.DIALOG_DESTROY_WITH_PARENT,
                gtk.MESSAGE_WARNING,
                gtk.BUTTONS_OK,
                text)
        d.run()
        d.destroy()

    def set_files(self, files):
        """Set num panes to len(files) and load each file given.
           If an element is None, the text of a pane is left"""
        gtk.idle_add( self._set_files_internal(files).next )

    def _set_files_internal(self, files):
        self.set_num_panes( len(files) )
        self._disconnect_buffer_handlers()
        self.linediffer.diffs = [[],[]]
        self.refresh()
        buffers = [t.get_buffer() for t in self.textview][:self.num_panes]
        try_codecs = ["utf8", "latin1"]
        yield "Opening files"
        panetext = ["\n"] * self.num_panes
        tasks = []
        for i,f in misc.enumerate(files):
            if f:
                buffers[i].delete( buffers[i].get_start_iter(), buffers[i].get_end_iter() )
                self.fileentry[i].set_filename(f)
                try:
                    task = misc.struct(filename = f,
                                       file = codecs.open(f, "r", try_codecs[0]),
                                       buf = buffers[i],
                                       codec = try_codecs[:],
                                       text = [],
                                       pane = i)
                    tasks.append(task)
                except IOError, e:
                    self._set_text( "", filename, pane)
                    self._dialog("Could not open '%s' for reading.\n\nThe error was:\n%s" % (filename, str(e)) )
            else:
                panetext[i] = buffers[i].get_text( buffers[i].get_start_iter(), buffers[i].get_end_iter() )
        self.label_changed()
        yield "Reading files"
        while len(tasks):
            for t in tasks[:]:
                try:
                    nextbit = t.file.read(4096)
                except ValueError, err:
                    t.codec.pop(0)
                    if len(t.codec):
                        t.file = codecs.open(t.filename, "r", t.codec[0])
                        t.buf.delete( t.buf.get_start_iter(), t.buf.get_end_iter() )
                        t.text = []
                    else:
                        print "codec error fallback", err
                        t.buf.delete( t.buf.get_start_iter(), t.buf.get_end_iter() )
                        self._dialog("Could not read from '%s'.\n\nI tried encodings %s."
                            % (t.filename, try_codecs))
                        tasks.remove(t)
                else:
                    if len(nextbit):
                        t.buf.insert( t.buf.get_end_iter(), nextbit )
                        t.text.append(nextbit)
                    else:
                        tasks.remove(t)
                        panetext[t.pane] = "".join(t.text)
            yield 1
        yield "Computing differences"
        lines = map(lambda x: x.split("\n"), panetext)
        step = self.linediffer.set_sequences_iter(*lines)
        while step.next() == None:
            yield 1
        self._connect_buffer_handlers()
        self.refresh()
        yield 0
        
    def save_file(self, pane):
        name = self.fileentry[pane].get_full_path(0)
        if not name:
            fselect = gtk.FileSelection("Choose a name for buffer %i" % pane)
            response = fselect.run()
            name = os.path.abspath(fselect.get_property("filename"))
            fselect.destroy()
            if response != gtk.RESPONSE_OK:
                return gnomeglade.RESULT_ERROR
            self.fileentry[pane].set_filename(name)
        buf = self.textview[pane].get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), 0)
        buf.meld_encoding = None
        if buf.meld_encoding:
            text = text.encode(buf.meld_encoding)
        try:
            open(name,"w").write(text)
        except IOError, e:
            self.statusbar.add_status("Error writing to %s (%s)." % (name,e))
            message = "Error writing to %s\n\n%s." % (name,e)
            d = gtk.MessageDialog(self.widget.get_toplevel(),
                gtk.DIALOG_DESTROY_WITH_PARENT,
                gtk.MESSAGE_ERROR,
                gtk.BUTTONS_OK,
                message)
            d.run()
            d.destroy()
            return gnomeglade.RESULT_ERROR
        else:
            self.undosequence.clear()
            self.set_buffer_modified(buf, 0)
            status = "Saved %s." % name
        self.statusbar.add_status(status)
        return gnomeglade.RESULT_OK

    def set_buffer_writable(self, buf, yesno):
        buf.set_data("writable", yesno)
        self.label_changed()

    def set_buffer_modified(self, buf, yesno):
        buf.set_data("modified", yesno)
        self.label_changed()

    def save_focused(self):
        for i in range(self.num_panes):
            t = self.textview[i]
            if t.is_focus():
                self.save_file(i)
                return
        self.statusbar.add_status("Click in the file you want to save")

    def save_all(self):
        for i in range(self.num_panes):
            if self.textview[i].get_buffer().get_data("modified"):
                self.save_file(i)

    def on_fileentry_activate(self, entry):
        files = [None] * self.num_panes
        files[ self.fileentry.index(entry) ] = entry.get_full_path(0)
        self.set_files(files)

        #
        # refresh, _queue_refresh
        #
    def refresh(self, junk=None):
        self.flushevents()
        text = []
        for i in range(self.num_panes):
            b = self.textview[i].get_buffer()
            t = b.get_text(b.get_start_iter(), b.get_end_iter(), 0)
            text.append(t)
        for i in range(self.num_panes-1):
            self.linkmap[i].queue_draw()
        for i in range(self.num_panes):
            self._highlight_buffer(i)
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
            line  = (adjustment.value + adjustment.page_size * syncpoint)
            line *= self._get_line_count(master)
            line /= (adjustment.upper - adjustment.lower) 

            for (i,adj) in others:
                mbegin,mend, obegin,oend = 0, self._get_line_count(master), 0, self._get_line_count(i)
                # look for the chunk containing 'line'
                for c in self.linediffer.pair_changes(master, i):
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
        madj = self.scrolledwindow[textindex].get_vadjustment()

        window = area.window
        window.clear()
        gctext = area.get_style().text_gc[0]
        '''style = area.get_style()
        gc = { "insert":style.light_gc[0],
               "delete":style.light_gc[0],
               "replace":style.light_gc[0],
               "conflict":style.dark_gc[3] }'''
        if not hasattr(area, "meldgc"):
            self._setup_gcs(area)

        gc = area.meldgc.get_gc
        for c in self.linediffer.single_changes(textindex):
            assert c[0] != "equal"
            s,e = ( scaleit(c[1]), scaleit(c[2]+(c[1]==c[2])) )
            s,e = math.floor(s), math.ceil(e)
            window.draw_rectangle( gc(c[0]), 1, x0, s, x1, e-s)
            window.draw_rectangle( gctext, 0, x0, s, x1, e-s)

    def on_diffmap_button_press_event(self, area, event):
        #TODO need height of arrow button on scrollbar - how do we get that?
        size_of_arrow = 14
        diffmapindex = self.diffmap.index(area)
        textindex = (0, self.num_panes-1)[diffmapindex]
        textview = self.textview[textindex]
        textheight = textview.get_allocation().height
        fraction = (event.y - size_of_arrow) / (textheight - 2*size_of_arrow)
        linecount = self._get_line_count(textindex)
        wantline = misc.clamp(fraction * linecount, 0, linecount)
        iter = textview.get_buffer().get_iter_at_line(wantline)
        self.textview[textindex].scroll_to_iter(iter, 0.0, use_align=1, xalign=0, yalign=0.5)

    def _highlight_buffer(self, which):
        widget = self.textview[which]
        buffer = widget.get_buffer()

        tag_delete_line = _ensure_fresh_tag_exists("delete line", buffer,
                {"background": self.prefs.color_deleted}  )
        tag_replace_line = _ensure_fresh_tag_exists("replace line", buffer,
                {"background": self.prefs.color_changed} )
        tag_conflict_line = _ensure_fresh_tag_exists("conflict line", buffer,
                {"background": self.prefs.color_conflict} )

        for c in self.linediffer.single_changes(which):
            if c[1] != c[2]:
                start = buffer.get_iter_at_line(c[1])
                end   = buffer.get_iter_at_line(c[2])
                if c[0] == "insert":
                    buffer.apply_tag(tag_delete_line, start, end)
                elif c[0] == "replace":
                    buffer.apply_tag(tag_replace_line, start, end)
                elif c[0] == "delete":
                    buffer.apply_tag(tag_delete_line, start, end)
                elif c[0] == "conflict":
                    buffer.apply_tag(tag_conflict_line, start, end)

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
                if self.textview[i].get_buffer().get_data("modified"):
                    self.statusimage[i].show()
            self.refresh()
            self.label_changed()
        
    def next_diff(self, direction):
        adjs = map( lambda x: x.get_vadjustment(), self.scrolledwindow)
        line = (adjs[1].value + adjs[1].page_size/2) / self.pixels_per_line
        c = None
        if direction == gdk.SCROLL_DOWN:
            for c in self.linediffer.single_changes(1):
                assert c[0] != "equal"
                if c[1] > line:
                    break
        else: #direction == gdk.SCROLL_UP
            for chunk in self.linediffer.single_changes(1):
                if chunk[2] < line:
                    c = chunk
                elif c:
                    break
        if c:
            if c[2] - c[1]: # no range, use other side
                l = c[1]+c[2]
                a = adjs[1]
            else:
                l = c[3]+c[4]
                a = adjs[c[5]]
            want = 0.5 * (self.pixels_per_line * l - a.page_size)
            want = misc.clamp(want, 0, a.upper-a.page_size)
            a.set_value( want )

    def _setup_gcs(self, area):
        assert area.window
        gcd = area.window.new_gc()
        gcd.set_rgb_fg_color( gdk.color_parse(self.prefs.color_deleted) )
        gcc = area.window.new_gc()
        gcc.set_rgb_fg_color( gdk.color_parse(self.prefs.color_changed) )
        gce = area.window.new_gc()
        gce.set_rgb_fg_color( gdk.color_parse(self.prefs.color_edited) )
        gcx = area.window.new_gc()
        gcx.set_rgb_fg_color( gdk.color_parse(self.prefs.color_conflict) )
        area.meldgc = misc.struct(gc_delete=gcd, gc_insert=gcd, gc_replace=gcc, gc_conflict=gcx)
        area.meldgc.get_gc = lambda p: getattr(area.meldgc, "gc_"+p)

        #
        # linkmap drawing
        #
    def on_linkmap_expose_event(self, area, event):
        window = area.window
        # not mapped? 
        if not window: return
        alloc = area.get_allocation()
        (wtotal,htotal) = alloc.width, alloc.height
        
        if not hasattr(area, "meldgc"):
            self._setup_gcs(area)
        gctext = area.get_style().text_gc[0]
        window.clear()

        which = self.linkmap.index(area)
        madj = self.scrolledwindow[which  ].get_vadjustment()
        oadj = self.scrolledwindow[which+1].get_vadjustment()

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
        for c in self.linediffer.pair_changes(which, which+1):
            assert c[0] != "equal"
            f0,f1 = map( lambda l: l * self.pixels_per_line - madj.value, c[1:3] )
            t0,t1 = map( lambda l: l * self.pixels_per_line - oadj.value, c[3:5] )
            if f1<0 and t1<0: # find first visible chunk
                continue
            if f0>htotal and t0>htotal: # we've gone past last visible
                break
            if f0==f1: f0 -= 2; f1 += 2
            if t0==t1: t0 -= 2; t1 += 2
            if draw_style > 0:
                n = (1.0, 9.0)[draw_style-1]
                points0 = []
                points1 = [] 
                for t in map(lambda x: x/n, range(n+1)):
                    points0.append( (    t*wtotal, (1-f(t))*f0 + f(t)*t0 ) )
                    points1.append( ((1-t)*wtotal, f(t)*f1 + (1-f(t))*t1 ) )

                points = points0 + points1 + [points0[0]]

                window.draw_polygon( gc(c[0]), 1, points)
                window.draw_lines(gctext, points0  )
                window.draw_lines(gctext, points1  )
            else:
                w = wtotal
                p = self.pixbuf_apply0.get_width()
                window.draw_polygon(gctext, 0, (( -1, f0), (  p, f0), (  p,f1), ( -1,f1)) )
                window.draw_polygon(gctext, 0, ((w+1, t0), (w-p, t0), (w-p,t1), (w+1,t1)) )
                points0 = (0,f0), (0,t0)
                window.draw_line( gctext, p, 0.5*(f0+f1), w-p, 0.5*(t0+t1) )

            x = wtotal-self.pixbuf_apply0.get_width()
            if c[0]=="insert":
                pix1.render_to_drawable( window, gctext, 0,0, x, points0[-1][1], -1,-1, 0,0,0)
            elif c[0] == "delete":
                pix0.render_to_drawable( window, gctext, 0,0, 0, points0[ 0][1], -1,-1, 0,0,0)
            else: #replace
                pix0.render_to_drawable( window, gctext, 0,0, 0, points0[ 0][1], -1,-1, 0,0,0)
                pix1.render_to_drawable( window, gctext, 0,0, x, points0[-1][1], -1,-1, 0,0,0)

        # allow for scrollbar at end of textview
        mid = 0.5 * self.textview0.get_allocation().height
        window.draw_line(gctext, .25*wtotal, mid,.75*wtotal, mid)

    def on_linkmap_scroll_event(self, area, event):
        self.next_diff(event.direction)

    def on_linkmap_button_press_event(self, area, event):
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
        adj = self.scrolledwindow[which+side].get_vadjustment()
        func = lambda c: c[1] * self.pixels_per_line - adj.value

        src = which + side
        dst = which + 1 - side
        for c in self.linediffer.pair_changes(src,dst):
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

    def on_linkmap_button_release_event(self, area, event):
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

gobject.type_register(FileDiff)
