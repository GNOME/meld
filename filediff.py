#! python
import math
import gtk
import gobject

import diffutil
import gnomeglade
import misc
import undo

#XXX
import difflib

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
        b.insert( b.get_iter_at_offset( self.offset), self.text, len(self.text)) 

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
        b.insert( b.get_iter_at_offset( self.offset), self.text, len(self.text)) 
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
class FileDiff(gnomeglade.Component):
    """Two or three way diff of text files"""

    __gsignals__ = {
        'label-changed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_STRING,))
    }

    def __init__(self, numpanes, statusbar):
        self.__gobject_init__()
        gnomeglade.Component.__init__(self, misc.appdir("glade2/filediff.glade"), "filediff")
        self._map_widgets_into_lists( ["textview", "fileentry", "diffmap", "scrolledwindow", "linkmap"] )
        self.numpanes = 0
        self.set_num_panes(numpanes)
        self.statusbar = statusbar
        self.undosequence = undo.UndoSequence()
        self.undosequence_busy = 0
        self.prefs = misc.struct(
            deleted_color="#ffff00",
            changed_color="#ffff00",
            edited_color="#cccccc",
            conflict_color="#ff0000")

        for i in range(self.numpanes):
            w = self.scrolledwindow[i]
            w.get_vadjustment().connect("value-changed", self._sync_vscroll )
            w.get_hadjustment().connect("value-changed", self._sync_hscroll )
            self.textview[i].get_buffer().connect("insert-text", self.on_text_insert_text)
            self.textview[i].get_buffer().connect("delete-range", self.on_text_delete_range)

        self.linediffs = diffutil.Differ()
        self.refresh_timer_id = -1
        self.pixbuf0 = gnomeglade.load_pixbuf(misc.appdir("glade2/apply0.xpm"))
        self.pixbuf1 = gnomeglade.load_pixbuf(misc.appdir("glade2/apply1.xpm"))
        for l in self.linkmap: # glade bug? specified in file
            l.set_events(gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.BUTTON_RELEASE_MASK)


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
            self._queue_refresh()
    def on_text_delete_range(self, buffer, iter0, iter1):
        if not self.undosequence_busy:
            self.undosequence.begin_group()
            if buffer.get_data("modified") != 1:
                self.undosequence.add_action( BufferModifiedAction(buffer, self) )
            text = buffer.get_text(iter0, iter1, 0)
            self.undosequence.add_action( BufferDeletionAction(buffer, iter0.get_offset(), text) )
            self.undosequence.end_group()
            self._queue_refresh()

    def undo(self):
        if self.undosequence.can_undo():
            self.undosequence_busy = 1
            try:
                self.undosequence.undo()
            finally:
                self.undosequence_busy = 0
            self._queue_refresh(0)
    def redo(self):
        if self.undosequence.can_redo():
            self.undosequence_busy = 1
            try:
                self.undosequence.redo()
            finally:
                self.undosequence_busy = 0
            self.undosequence_busy = 0
            self._queue_refresh(0)

        #
        # text buffer loading/saving
        #
    def set_text(self, text, filename, pane, editable=1):
        view = self.textview[pane]
        buffer = view.get_buffer()
        buffer.set_text( text )
        _ensure_fresh_tag_exists("edited line", buffer, {"background": self.prefs.edited_color } )
        entry = self.fileentry[pane]
        entry.set_filename(filename)
        view.set_editable(editable)
        self.undosequence.clear()
        self.set_buffer_modified(buffer, 0)

    def label_changed(self):
        filenames = []
        for i in range(self.numpanes):
            f = self.fileentry[i].get_full_path(0) or ""
            m = self.textview[i].get_buffer().get_data("modified") and "*" or ""
            filenames.append( f+m )
        labeltext = " : ".join( misc.shorten_names(*filenames)) + " "
        self.emit("label-changed", labeltext)

    def set_file(self, filename, pane):
        self.fileentry[pane].set_filename(filename)
        try:
            text = open(filename).read()
            self.set_text( text, filename, pane, 1)
            self.statusbar.add_status( "Read %s" % filename )
        except IOError, e:
            self.set_text( "", filename, pane, 0)
            self.statusbar.add_status( str(e) )

    def save_file(self, pane):
        name = self.fileentry[pane].get_full_path(0)
        buf = self.textview[pane].get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), 0)
        try:
            open(name,"w").write(text)
        except IOError, e:
            status = "Error writing to %s (%s)." % (name,e)
        else:
            self.undosequence.clear()
            self.set_buffer_modified(buf, 0)
            status = "Saved %s." % name
        self.statusbar.add_status(status)

    def set_buffer_modified(self, buf, yesno):
        buf.set_data("modified", yesno)
        self.label_changed()

    def save(self):
        for i in range(self.numpanes):
            t = self.textview[i]
            if t.is_focus():
                self.save_file(i)
                return
        self.statusbar.add_status("Click in the file you want to save")

    def on_fileentry_activate(self, entry):
        pane = self.fileentry.index(entry)
        file = entry.get_full_path(0)
        self.set_file(file, pane)

        #
        # refresh, _queue_refresh
        #
    def refresh(self, junk=None):
        if self.refresh_timer_id != -1:
            gtk.timeout_remove(self.refresh_timer_id)
            self.refresh_timer_id = -1
        self.flushevents()
        text = []
        for i in range(self.numpanes):
            b = self.textview[i].get_buffer()
            t = b.get_text(b.get_start_iter(), b.get_end_iter(), 0)
            text.append(t)
        self.linediffs = apply(diffutil.Differ,text)
        for i in range(self.numpanes-1):
            self.linkmap[i].queue_draw()
        for i in range(self.numpanes):
            self._highlight_buffer(i)
        self.diffmap0.queue_draw()
        self.diffmap1.queue_draw()

    def _queue_refresh(self, delay=1000):
        if self.refresh_timer_id != -1:
            gtk.timeout_remove(self.refresh_timer_id)
            self.refresh_timer_id = -1
        if delay:
            self.refresh_timer_id = gtk.timeout_add(delay, self.refresh, 0)
        else:
            self.refresh()

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
            adjustments = adjustments[:self.numpanes]
            master = adjustments.index(adjustment)
            # scrollbar influence 0->1->2 or 0<-1<-2 or 0<-1->2
            others = zip( range(self.numpanes), adjustments)
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
                for c in self.linediffs.pair_changes(master, i):
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
                val = min(val, adj.upper - adj.page_size)
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
        textindex = (0, self.numpanes-1)[diffmapindex]

        #TODO height of arrow button on scrollbar - how do we get that?
        #TODO get font height 
        size_of_arrow = 14
        hperline = float( self.scrolledwindow[textindex].get_allocation().height - 3*size_of_arrow) / self._get_line_count(textindex)
        if hperline > 11:
            hperline = 11

        scaleit = lambda x,s=hperline,o=size_of_arrow: x*s+o
        x0 = 4
        x1 = area.get_allocation().width - 2*x0
        madj = self.scrolledwindow[textindex].get_vadjustment()

        window = area.window
        window.clear()
        style = area.get_style()
        #if not hasattr(style, "meld_gc"):
        #   setattr(style, "meld_gc", [])
        #   a = gtk.gdk.GC()
        gc = { "insert":style.light_gc[0],
               "delete":style.light_gc[0],
               "replace":style.light_gc[0],
               "conflict":style.dark_gc[3] }

        for c in self.linediffs.single_changes(textindex):
            s,e = ( scaleit(c[1]), scaleit(c[2]+(c[1]==c[2])) )
            s,e = math.floor(s), math.ceil(e)
            window.draw_rectangle(gc[c[0]], 1, x0, s, x1, e-s)

    def _highlight_buffer(self, which):
        widget = self.textview[which]
        buffer = widget.get_buffer()

        tag_delete_line = _ensure_fresh_tag_exists("delete line", buffer,
                {"background": self.prefs.deleted_color }  )
        tag_replace_line = _ensure_fresh_tag_exists("replace line", buffer,
                {"background": self.prefs.changed_color } )
        tag_conflict_line = _ensure_fresh_tag_exists("conflict line", buffer,
                {"background": self.prefs.conflict_color } )

        for c in self.linediffs.single_changes(which):
            start = buffer.get_iter_at_line(c[1])
            end =   buffer.get_iter_at_line(c[2])
            if c[0] == "replace":
                buffer.apply_tag(tag_replace_line, start,end)
            elif c[0] == "delete":
                buffer.apply_tag(tag_delete_line, start,end)
            elif c[0] == "conflict":
                buffer.apply_tag(tag_conflict_line, start,end)

    def _get_line_count(self, index):
        """Return the number of lines in the buffer of textview 'text'"""
        return self.textview[index].get_buffer().get_line_count()

    def set_num_panes(self, numpanes):
        if numpanes != self.numpanes and numpanes in (2,3):
            if numpanes == 2:
                self.linkmap1.hide()
                self.scrolledwindow2.hide()
                self.fileentry2.hide()
            else:
                self.linkmap1.show()
                self.scrolledwindow2.show()
                self.fileentry2.show()
            self.numpanes = numpanes
        
    def next_diff(self, direction):
        adj = self.scrolledwindow1.get_vadjustment()

        pixels_per_line = (adj.upper - adj.lower) / self._get_line_count(1)
        line = (adj.value + adj.page_size/2) / pixels_per_line

        if direction == gtk.gdk.SCROLL_DOWN:
            for c in self.linediffs.single_changes(1):
                if c[1] > line:
                    want = 0.5 * (pixels_per_line * (c[1] + c[2]) - adj.page_size)
                    adj.set_value( want )
                    return
        else: #direction == gtk.gdk.SCROLL_UP
            save = None
            for c in self.linediffs.single_changes(1):
                if c[2] < line:
                    save = c
                else:
                    if save:
                        want = 0.5 * (pixels_per_line * (save[1]+save[2]) - adj.page_size)
                        adj.set_value( want )
                        return

        #
        # linkmap drawing
        #
    def on_linkmap_expose_event(self, area, event):
        window = area.window
        # not mapped? 
        if not window: return
        alloc = area.get_allocation()
        (wtotal,htotal) = alloc.width, alloc.height
        
        # sync bar
        style = area.get_style()
        gcfg = style.light_gc[0]
        window.clear()

        which = self.linkmap.index(area)
        madj = self.scrolledwindow[which  ].get_vadjustment()
        oadj = self.scrolledwindow[which+1].get_vadjustment()
        pixels_per_line = (madj.upper - madj.lower) / self._get_line_count(which)
        if pixels_per_line > 15: #TODO use real font height
            pixels_per_line = 15
        indent = 8

        # gain function for smoothing
        #TODO cache these values
        bias = lambda x,g: math.pow(x, math.log(g) / math.log(0.5))
        def gain(t,g):
            if t<0.5:
                return bias(2*t,1-g)/2.0
            else:
                return (2-bias(2-2*t,1-g))/2.0
        f = lambda x: gain( x, 0.85)

        for c in self.linediffs.pair_changes(which, which+1):
            f0,f1 = map( lambda l: l * pixels_per_line - madj.value, c[1:3] )
            t0,t1 = map( lambda l: l * pixels_per_line - oadj.value, c[3:5] )
            if f1<0 and t1<0: # find first visible chunk
                continue
            if f0>htotal and t0>htotal: # we've gone past last visible
                break
            if f0==f1: f0 -= 2; f1 += 2
            if t0==t1: t0 -= 2; t1 += 2
            n = 1.0 #TODO cache
            points0 = []
            points1 = [] 
            for t in map(lambda x: x/n, range(n+1)):
                points0.append( (    t*wtotal, (1-f(t))*f0 + f(t)*t0 ) )
                points1.append( ((1-t)*wtotal, f(t)*f1 + (1-f(t))*t1 ) )

            points = points0 + points1 + [points0[0]]

            window.draw_polygon(gcfg, 1, points)
            window.draw_lines(style.text_gc[0], points0  )
            window.draw_lines(style.text_gc[0], points1  )

            if self.numpanes == 3: # 3way buggy
                continue
            x = wtotal-self.pixbuf0.get_width()
            if c[0]=="insert":
                self.pixbuf1.render_to_drawable( window, gcfg, 0,0, x, points0[-1][1], -1,-1, 0,0,0)
            elif c[0] == "delete":
                self.pixbuf0.render_to_drawable( window, gcfg, 0,0, 0, points0[ 0][1], -1,-1, 0,0,0)
            else: #replace
                self.pixbuf0.render_to_drawable( window, gcfg, 0,0, 0, points0[ 0][1], -1,-1, 0,0,0)
                self.pixbuf1.render_to_drawable( window, gcfg, 0,0, x, points0[-1][1], -1,-1, 0,0,0)
        window.draw_line(style.text_gc[0], .25*wtotal, 0.5*htotal,.75*wtotal, 0.5*htotal)

    def on_linkmap_scroll_event(self, area, event):
        self.next_diff(event.direction)

    def on_linkmap_button_press_event(self, area, event):
        if self.numpanes != 2: # 3way merge is buggy
            return
        self.mouse_chunk = None
        alloc = area.get_allocation()
        (wtotal,htotal) = alloc.width, alloc.height
        pw = self.pixbuf0.get_width()
        if event.x < pw:
            which = 0
        elif event.x > wtotal - pw:
            which = 1
        else:
            return
        
        madj = self.scrolledwindow0.get_vadjustment()
        oadj = self.scrolledwindow1.get_vadjustment()
        pixels_per_line = (madj.upper - madj.lower) / self._get_line_count(0)
        window = area.window
        style = area.get_style()
        gcfg = style.light_gc[0]

        ph = self.pixbuf0.get_height()
        if which==0:
            #for c in filter( lambda x: x[0]=="replace" or x[0]=="delete", self.linediffs):
            for c in self.linediffs.pair_changes(0,1):
                if c[0] == "insert":
                    continue
                f0 = c[1] * pixels_per_line - madj.value
                if f0<0: # find first visible chunk
                    continue
                if f0>htotal: # we've gone past last visible
                    break
                if f0 < event.y and event.y < f0 + ph:
                    #self.pixbuf1.render_to_drawable( window, gcfg, 0,0, 0, f0, -1,-1, 0,0,0)
                    self.mouse_chunk = (0, c)
                    break
        else:
            #for c in filter( lambda x: x[0]=="replace" or x[0]=="insert", self.linediffs):
            for c in self.linediffs.pair_changes(0,1):
                if c[0] == "delete":
                    continue
                t0 = c[3] * pixels_per_line - oadj.value
                if t0<0: # find first visible chunk
                    continue
                if t0>htotal: # we've gone past last visible
                    break
                if t0 < event.y and event.y < t0 + ph:
                    #self.pixbuf0.render_to_drawable( window, gcfg, 0,0, wtotal-pw, t0, -1,-1, 0,0,0)
                    self.mouse_chunk = (1, c)
                    break

    def on_linkmap_button_release_event(self, area, event):
        if self.numpanes != 2: # 3way merge is buggy
            return
        if self.mouse_chunk:
            pw = self.pixbuf0.get_width()
            wtotal = area.get_allocation().width
            # check we're still in button
            if (event.x < pw) or (wtotal - pw < event.x):
                ph = self.pixbuf0.get_height()
                which, c = self.mouse_chunk
                madj = self.scrolledwindow0.get_vadjustment()
                oadj = self.scrolledwindow1.get_vadjustment()
                pixels_per_line = (madj.upper - madj.lower) / self._get_line_count(0)
                f0 = c[1] * pixels_per_line - madj.value
                t0 = c[3] * pixels_per_line - oadj.value
                if which==0 and f0 < event.y and event.y < f0 + ph:
                    b0 = self.textview0.get_buffer()
                    t0 = b0.get_text( b0.get_iter_at_line(c[1]), b0.get_iter_at_line(c[2]), 0)
                    b1 = self.textview1.get_buffer()
                    self.on_text_begin_user_action()
                    b1.delete(b1.get_iter_at_line(c[3]), b1.get_iter_at_line(c[4]))
                    b1.insert_with_tags_by_name(b1.get_iter_at_line(c[3]), t0, "edited line")
                    self.on_text_end_user_action()
                    self._queue_refresh(0)
                if which==1 and t0 < event.y and event.y < t0 + ph:
                    b1 = self.textview1.get_buffer()
                    t1 = b1.get_text( b1.get_iter_at_line(c[3]), b1.get_iter_at_line(c[4]), 0)
                    b0 = self.textview0.get_buffer()
                    self.on_text_begin_user_action()
                    b0.delete(b0.get_iter_at_line(c[1]), b0.get_iter_at_line(c[2]))
                    b0.insert_with_tags_by_name(b0.get_iter_at_line(c[1]), t1, "edited line")
                    self.on_text_end_user_action()
                    self._queue_refresh(0)
            self.mouse_chunk = None

gobject.type_register(FileDiff)
