## python
import math
import gtk
import gobject

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

def _clamp(val, lower, upper):
    assert lower <= upper
    return min( max(val, lower), upper)

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

MASK_SHIFT, MASK_CTRL, MASK_ALT = 1, 2, 3

class FileDiff(gnomeglade.Component):
    """Two or three way diff of text files"""

    __gsignals__ = {
        'label-changed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_STRING,)),
        'working-hard': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_INT,))
    }

    keylookup = {65505 : MASK_SHIFT, 65507 : MASK_CTRL, 65513: MASK_ALT}

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
            deleted_color="#ffffcc",
            changed_color="#ffffcc",
            edited_color="#eeeeee",
            conflict_color="#ffcccc")
        self.keymask = 0

        for i in range(self.numpanes):
            w = self.scrolledwindow[i]
            w.get_vadjustment().connect("value-changed", self._sync_vscroll )
            w.get_hadjustment().connect("value-changed", self._sync_hscroll )
            self.textview[i].get_buffer().connect("insert-text", self.on_text_insert_text)
            self.textview[i].get_buffer().connect("delete-range", self.on_text_delete_range)
            if 0: # test different font sizes
                description = self.textview[i].get_pango_context().get_font_description()
                description.set_size(17 * 1024)
                self.textview[i].modify_font(description)

        context = self.textview0.get_pango_context()
        metrics = context.get_metrics( context.get_font_description(), context.get_language() )
        self.pixels_per_line = (metrics.get_ascent() + metrics.get_descent()) / 1024

        self.linediffs = diffutil.Differ()
        self.refresh_timer_id = -1
        self.pixbuf_apply0 = gnomeglade.load_pixbuf(misc.appdir("glade2/button_apply0.xpm"))
        self.pixbuf_apply1 = gnomeglade.load_pixbuf(misc.appdir("glade2/button_apply1.xpm"))
        self.pixbuf_delete = gnomeglade.load_pixbuf(misc.appdir("glade2/button_delete.xpm"))
        self.pixbuf_copy0  = gnomeglade.load_pixbuf(misc.appdir("glade2/button_copy0.xpm"))
        self.pixbuf_copy1  = gnomeglade.load_pixbuf(misc.appdir("glade2/button_copy1.xpm"))

        for l in self.linkmap: # glade bug workaround
            l.set_events(gdk.BUTTON_PRESS_MASK | gdk.BUTTON_RELEASE_MASK)


    def on_key_press_event(self, object, event):
        for t in self.textview: # key event bug workaround
            if t.is_focus() and object != t:
                return
        x = self.keylookup.get(event.keyval, 0)
        self.keymask |= x
        for l in self.linkmap[:self.numpanes-1]:
            a = l.get_allocation()
            l.queue_draw_area(0,       0, 16, a[3])
            l.queue_draw_area(a[2]-16, 0, 16, a[3])
    def on_key_release_event(self, object, event):
        for t in self.textview: # key event bug workaround
            if t.is_focus() and object != t:
                return
        x = self.keylookup.get(event.keyval, 0)
        self.keymask &= ~x
        for l in self.linkmap[:self.numpanes-1]:
            a = l.get_allocation()
            l.queue_draw_area(0,       0, 16, a[3])
            l.queue_draw_area(a[2]-16, 0, 16, a[3])

    def on_linkmap_focus_in_event(self, *args):
        print args
        return 1
    def on_linkmap_focus_out_event(self, *args):
        print args
        return 1

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
                val = _clamp(val, 0, adj.upper - adj.page_size)
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

        #TODO this is wrong
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
        style = area.get_style()
        #if not hasattr(style, "meld_gc"):
        #   setattr(style, "meld_gc", [])
        #   a = gdk.GC()
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
            if c[0] == "insert" or c[0] == "replace":
                buffer.apply_tag(tag_replace_line, start,end)
            elif c[0] == "delete":
                buffer.apply_tag(tag_delete_line, start,end)
            elif c[0] == "conflict":
                buffer.apply_tag(tag_conflict_line, start,end)

    def _get_line_count(self, index):
        """Return the number of lines in the buffer of textview 'text'"""
        return self.textview[index].get_buffer().get_line_count()

    def set_num_panes(self, numpanes):
        if numpanes != self.numpanes and numpanes in (1,2,3):
            if numpanes == 1:
                map( lambda x: x.hide(), self.linkmap + self.scrolledwindow[1:] + self.fileentry[1:])
            elif numpanes == 2:
                self.linkmap1.hide()
                self.scrolledwindow2.hide()
                self.fileentry2.hide()
            else:
                self.linkmap1.show()
                self.scrolledwindow2.show()
                self.fileentry2.show()
            self.numpanes = numpanes
        
    def next_diff(self, direction):
        adjs = map( lambda x: x.get_vadjustment(), self.scrolledwindow)
        line = (adjs[1].value + adjs[1].page_size/2) / self.pixels_per_line
        c = None

        if direction == gdk.SCROLL_DOWN:
            for c in self.linediffs.single_changes(1):
                if c[1] > line:
                    break
        else: #direction == gdk.SCROLL_UP
            save = None
            for chunk in self.linediffs.single_changes(1):
                if chunk[2] < line:
                    c = chunk
                elif c:
                    break
        if c:
            if c[2] - c[1]:
                l = c[1]+c[2]
                a = adjs[1]
            else:
                l = c[3]+c[4]
                a = adjs[c[5]]
            want = 0.5 * (self.pixels_per_line * l - a.page_size)
            want = _clamp(want, 0, a.upper-a.page_size)
            a.set_value( want )

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

        if self.keymask & MASK_SHIFT:
            pix0 = self.pixbuf_delete
            pix1 = self.pixbuf_delete
        elif self.keymask & MASK_CTRL:
            pix0 = self.pixbuf_copy0
            pix1 = self.pixbuf_copy1
        else: # self.keymask == 0:
            pix0 = self.pixbuf_apply0
            pix1 = self.pixbuf_apply1

        for c in self.linediffs.pair_changes(which, which+1):
            f0,f1 = map( lambda l: l * self.pixels_per_line - madj.value, c[1:3] )
            t0,t1 = map( lambda l: l * self.pixels_per_line - oadj.value, c[3:5] )
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

            x = wtotal-self.pixbuf_apply0.get_width()
            if c[0]=="insert":
                pix1.render_to_drawable( window, gcfg, 0,0, x, points0[-1][1], -1,-1, 0,0,0)
            elif c[0] == "delete":
                pix0.render_to_drawable( window, gcfg, 0,0, 0, points0[ 0][1], -1,-1, 0,0,0)
            else: #replace
                pix0.render_to_drawable( window, gcfg, 0,0, 0, points0[ 0][1], -1,-1, 0,0,0)
                pix1.render_to_drawable( window, gcfg, 0,0, x, points0[-1][1], -1,-1, 0,0,0)
        # allow for scrollbar at end of textview
        mid = 0.5 * self.textview0.get_allocation().height
        window.draw_line(style.text_gc[0], .25*wtotal, mid,.75*wtotal, mid)

    def on_linkmap_scroll_event(self, area, event):
        self.next_diff(event.direction)

    def on_linkmap_button_press_event(self, area, event):
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
            return
        adj = self.scrolledwindow[which+side].get_vadjustment()
        func = lambda c: c[1] * self.pixels_per_line - adj.value

        src = which + side
        dst = which + 1 - side
        for c in self.linediffs.pair_changes(src,dst):
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
        print self.mouse_chunk

    def on_linkmap_button_release_event(self, area, event):
        if self.mouse_chunk:
            (src,dst), rect, chunk = self.mouse_chunk
            # check we're still in button
            inrect = lambda p, r: ((r[0] < p.x) and (p.x < r[0]+r[2]) and (r[1] < p.y) and (p.y < r[1]+r[3]))
            if inrect(event, rect):
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

gobject.type_register(FileDiff)
