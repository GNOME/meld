#! /usr/bin/env python2.2

import os
import re
import stat
import time
import sys
import difflib
import math
sys.path.append("/home/stephen/garnome/lib/python2.2/site-packages")

import gobject
import gtk
import gtk.glade
import gnome
import gnome.ui
import gnomeglade


################################################################################
#
# Struct
#
################################################################################
class struct:
    def __init__(self, **args):
        self.__dict__.update(args)
    def __repr__(self):
        r = ["<"]
        for i in self.__dict__.keys():
            r.append("%s=%s" % (i, getattr(self,i)))
        r.append(">\n")
        return " ".join(r)


def look(s, o):
    return filter(lambda x:x.find(s)!=-1, dir(o))
#print filter(lambda x:x.find("MASK")!=-1, dir(gtk.gdk))
#print filter(lambda x:x.lower().find("wheel")!=-1, dir(gtk.gdk))
#print filter(lambda x:x.find("RUN")!=-1, dir(gobject))
################################################################################
#
# FileDiff2
#
################################################################################
class FileDiff2(gnomeglade.Component):
    __gsignals__ = { 'files-loaded': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_STRING, gobject.TYPE_STRING)) }

    def __init__(self):
        self.__gobject_init__()
        gnomeglade.Component.__init__(self, "glade2/filediff2.glade", "filediff2")
        self.linediffs = []
        sizegroup = gtk.SizeGroup(1)
        sizegroup.add_widget(self.textview0)
        sizegroup.add_widget(self.textview1)
        self.scrolledwindow0.get_vadjustment().connect("value-changed", lambda adj: self._sync_scroll(0) )
        self.scrolledwindow1.get_vadjustment().connect("value-changed", lambda adj: self._sync_scroll(1) )
        self.prefs = struct(deleted_color="#ebffeb", changed_color="#ebebff")
        self.prefs = struct(deleted_color="#ffaaaa", changed_color="#aaffaa", edited_color="#eeeeee")
        #targetlist = self.textview0.drag_dest_get_target_list()
        #(gtk.DEST_DEFAULT_ALL, [("text/uri-list", 0, 0)], gtk.gdk.ACTION_COPY)
        #self.textview0.drag_dest_set_target_list(targetlist)

        self.pixbuf0 = self._load_pixbuf("glade2/apply0.xpm")
        self.pixbuf1 = self._load_pixbuf("glade2/apply1.xpm")
        self.drawing2.add_events(gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.BUTTON_RELEASE_MASK)

    def on_drawing2_scroll_event(self, area, event):
        self.next_diff(event.direction)

    def next_diff(self, direction):
        madj = self.scrolledwindow0.get_vadjustment()
        oadj = self.scrolledwindow1.get_vadjustment()
        pixels_per_line = (madj.upper - madj.lower) / self._get_line_count(self.textview0)
        line0 = (madj.value + madj.page_size/2) / pixels_per_line
        line1 = (oadj.value + oadj.page_size/2) / pixels_per_line
        if direction == gtk.gdk.SCROLL_DOWN:
            comparison = lambda x: line0 < x[2]
            start, end, step = (0, len(self.linediffs), 1)
        else:
            comparison = lambda x: line0 > x[1]
            start,end, step = (len(self.linediffs)-1, -1, -1)

        ok = 1
        for i in xrange(start,end,step):
            c = self.linediffs[i]
            if c[0]=="equal" and comparison(c):
                ok = 1
            elif ok and comparison(c):
                if c[1] != c[2]:
                    v = (0.5 * pixels_per_line * (c[1]+c[2])) - madj.page_size/2
                else: # tricky, use the other adjustment if this range is empty
                    madj, oadj = oadj, madj
                    v = (0.5 * pixels_per_line * (c[3]+c[4])) - madj.page_size/2
                if v <= 0:
                    oadj.set_value(0)
                elif v > madj.upper-madj.page_size:
                    oadj.set_value( oadj.upper - oadj.page_size )
                else:
                    madj.set_value(v)
                break

            else:
                ok = 0

    def _load_pixbuf(self, fname):
        image = gtk.Image()
        image.set_from_file(fname)
        return image.get_pixbuf()

    def set_file(self, filename, which):
        view = (self.textview0, self.textview1)[which]
        try:
            lines = []
            for l in open(filename).read().split("\n"):
                lines.append( "%s%s"% (len(lines)%50==0 and "*"*80 or "",l) )
            text = "\n".join(lines)
        except IOError, e:
            print e
            text = ""
        buffer = view.get_buffer()
        buffer.set_text( text )
        self._ensure_fresh_tag_exists("edited line", buffer, {"background": self.prefs.edited_color } )
        entry = (self.fileentry0, self.fileentry1)[which]
        entry.set_filename(filename)
        f0 = self.fileentry0.get_full_path(0) or "None"
        f1 = self.fileentry1.get_full_path(0) or "None"
        self.emit("files-loaded", f0, f1)

    #def on_textview0_drag_data_received(self, text, context, x,y, typesel, id, time):
    def on_vbox0_drag_data_received(self, *args):
        print "**", dir(args[1])
    def on_fileentry0_activate(self, entry):
        self.set_file( entry.get_full_path(0), 0)
    def on_fileentry1_activate(self, entry):
        self.set_file( entry.get_full_path(0), 1)
    def on_drawing0_expose_event(self, area, event):
        self._draw_diff_map(self.drawing0, self.textview0, 0)
    def on_drawing1_expose_event(self, area, event):
        self._draw_diff_map(self.drawing1, self.textview1, 1)

    def on_drawing2_button_press_event(self, area, event):
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
        pixels_per_line = (madj.upper - madj.lower) / self._get_line_count(self.textview0)
        window = area.window
        style = area.get_style()
        gcfg = style.light_gc[0]

        #TODO move these traversals into a utility function or class
        ph = self.pixbuf0.get_height()
        if which==0:
            for c in filter( lambda x: x[0]=="replace" or x[0]=="delete", self.linediffs):
                f0 = c[1] * pixels_per_line - madj.value
                if f0<0: # find first visible chunk
                    continue
                if f0>htotal: # we've gone past last visible
                    break
                if f0 < event.y and event.y < f0 + ph:
                    self.pixbuf1.render_to_drawable( window, gcfg, 0,0, 0, f0, -1,-1, 0,0,0)
                    self.mouse_chunk = (0, c)
                    break
        else:
            for c in filter( lambda x: x[0]=="replace" or x[0]=="insert", self.linediffs):
                t0 = c[3] * pixels_per_line - oadj.value
                if t0<0: # find first visible chunk
                    continue
                if t0>htotal: # we've gone past last visible
                    break
                if t0 < event.y and event.y < t0 + ph:
                    self.pixbuf0.render_to_drawable( window, gcfg, 0,0, wtotal-pw, t0, -1,-1, 0,0,0)
                    self.mouse_chunk = (1, c)
                    break

    def on_drawing2_button_release_event(self, area, event):
        if self.mouse_chunk:
            pw = self.pixbuf0.get_width()
            wtotal = area.get_allocation().width
            # check we're still in button
            if (event.x < pw) or (wtotal - pw < event.x):
                ph = self.pixbuf0.get_height()
                which, c = self.mouse_chunk
                madj = self.scrolledwindow0.get_vadjustment()
                oadj = self.scrolledwindow1.get_vadjustment()
                pixels_per_line = (madj.upper - madj.lower) / self._get_line_count(self.textview0)
                f0 = c[1] * pixels_per_line - madj.value
                t0 = c[3] * pixels_per_line - oadj.value
                if which==0 and f0 < event.y and event.y < f0 + ph:
                    b0 = self.textview0.get_buffer()
                    t0 = b0.get_text( b0.get_iter_at_line(c[1]), b0.get_iter_at_line(c[2]), 0)
                    b1 = self.textview1.get_buffer()
                    b1.begin_user_action()
                    b1.delete(b1.get_iter_at_line(c[3]), b1.get_iter_at_line(c[4]))
                    b1.insert_with_tags_by_name(b1.get_iter_at_line(c[3]), t0, "edited line")
                    b1.end_user_action()
                    self.refresh()
                if which==1 and t0 < event.y and event.y < t0 + ph:
                    b1 = self.textview1.get_buffer()
                    t1 = b1.get_text( b1.get_iter_at_line(c[3]), b1.get_iter_at_line(c[4]), 0)
                    b0 = self.textview0.get_buffer()
                    b0.begin_user_action()
                    b0.delete(b0.get_iter_at_line(c[1]), b0.get_iter_at_line(c[2]))
                    b0.insert_with_tags_by_name(b0.get_iter_at_line(c[1]), t1, "edited line")
                    b0.end_user_action()
                    self.refresh()
            self.mouse_chunk = None

    def on_drawing2_expose_event(self, area, event):
        #print "expose", event, dir(event)
        window = area.window
        #print "*", area.get_events()
        # not mapped? 
        if not window: return
        alloc = area.get_allocation()
        (wtotal,htotal) = alloc.width, alloc.height
        
        # sync bar
        style = area.get_style()
        gcfg = style.light_gc[0]
        window.clear()

        madj = self.scrolledwindow0.get_vadjustment()
        oadj = self.scrolledwindow1.get_vadjustment()
        pixels_per_line = (madj.upper - madj.lower) / self._get_line_count(self.textview0)
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

        for c in filter( lambda x: x[0]!="equal", self.linediffs):
            f0,f1 = map( lambda l: l * pixels_per_line - madj.value, c[1:3] )
            t0,t1 = map( lambda l: l * pixels_per_line - oadj.value, c[3:5] )
            if f1<0 and t1<0: # find first visible chunk
                continue
            if f0>htotal and t0>htotal: # we've gone past last visible
                break
            if f0==f1: f0 -= 2; f1 += 2
            if t0==t1: t0 -= 2; t1 += 2
            n = 10.0 #TODO cache
            points0 = []
            points1 = [] 
            for t in map(lambda x: x/n, range(n+1)):
                points0.append( (    t*wtotal, (1-f(t))*f0 + f(t)*t0 ) )
                points1.append( ((1-t)*wtotal, f(t)*f1 + (1-f(t))*t1 ) )

            points = points0 + points1 + [points0[0]]

            window.draw_polygon(gcfg, 1, points)
            window.draw_lines(style.text_gc[0], points0  )
            window.draw_lines(style.text_gc[0], points1  )

            x = wtotal-self.pixbuf0.get_width()
            if c[0]=="insert":
                self.pixbuf1.render_to_drawable( window, gcfg, 0,0, x, points0[-1][1], -1,-1, 0,0,0)
            elif c[0] == "delete":
                self.pixbuf0.render_to_drawable( window, gcfg, 0,0, 0, points0[ 0][1], -1,-1, 0,0,0)
            else: #replace
                self.pixbuf0.render_to_drawable( window, gcfg, 0,0, 0, points0[ 0][1], -1,-1, 0,0,0)
                self.pixbuf1.render_to_drawable( window, gcfg, 0,0, x, points0[-1][1], -1,-1, 0,0,0)
        window.draw_line(style.text_gc[0], .25*wtotal,  0.5*htotal,.75*wtotal, 0.5*htotal)
        
    def refresh(self, *args):
        self.flushevents()
        b0 = self.textview0.get_buffer()
        t0 = b0.get_text(b0.get_start_iter(), b0.get_end_iter(), 0)
        b1 = self.textview1.get_buffer()
        t1 = b1.get_text(b1.get_start_iter(), b1.get_end_iter(), 0)
        self.linediffs = difflib.SequenceMatcher(None, t0.split("\n"), t1.split("\n")).get_opcodes()
        self._highlight_buffer(0)
        self._highlight_buffer(1)
        self.drawing0.queue_draw()
        self.drawing1.queue_draw()
        self.drawing2.queue_draw()

    def goto_top(self):
        tofrom = self.textview1.is_focus()
        text, index =  ((self.textview0, 1), (self.textview1, 3))[tofrom]
        buf = text.get_buffer()
        for c in self.linediffs:
            if c[0] != "equal":
                break
        text.scroll_to_iter( buf.get_iter_at_line(c[index]), 0.4, 1, 0.5, 0)
    def goto_bottom(self):
        tofrom = self.textview1.is_focus()
        text, index =  ((self.textview0, 1), (self.textview1, 3))[tofrom]
        buf = text.get_buffer()
        for c in self.linediffs:
            if c[0] != "equal":
                break
        text.scroll_to_iter( buf.get_iter_at_line(c[index]), 0.4, 1, 0.5, 0)

    def _highlight_buffer(self, which):
        base = (1,3)[which]
        chunk_delete = ("delete", "insert")[which]
        chunk_equal = "equal"
        chunk_replace = "replace"
        widget = (self.textview0, self.textview1)[which]
        buffer = widget.get_buffer()

        tag_delete_line = self._ensure_fresh_tag_exists("delete line", buffer,
                {"background": self.prefs.deleted_color }  )
        tag_replace_line = self._ensure_fresh_tag_exists("replace line", buffer,
                {"background": self.prefs.changed_color } )

        for c in self.linediffs:
            b,e = c[base],c[base+1]
            start = buffer.get_iter_at_line(b)
            end =   buffer.get_iter_at_line(e)
            if c[0] == chunk_replace:
                buffer.apply_tag(tag_replace_line, start,end)
            elif c[0] == chunk_delete:
                buffer.apply_tag(tag_delete_line, start,end)

    def _get_line_count(self, text):
        return text.get_buffer().get_line_count()

    def _draw_diff_map(self, drawing, text, which):
        XXXX = 14 #TODO height of arrow button on scrollbar - how do we get that?
        offset = self.fileentry0.get_allocation()[3] + XXXX
        hperline = float( text.get_allocation()[3] - 2*XXXX) / self._get_line_count(text)
        if hperline > 11: #TODO font height 
            hperline = 11
        scaleit = lambda x,s=hperline,o=offset: x*s+o
        x0 = 4
        x1 = drawing.get_allocation()[2] - 2*x0
        base = (1,3)[which]
        madj = self.scrolledwindow0.get_vadjustment()

        window = drawing.window
        window.clear()
        style = drawing.get_style()
        gc = { "insert":style.light_gc[0],
               "delete":style.light_gc[0],
               "replace":style.dark_gc[0] }
        for c in filter(lambda x: x[0]!='equal', self.linediffs):
            (s,e) = c[base:base+2]
            e += s==e
            (s,e) = map( scaleit, (s,e) )
            s = math.floor(s)
            e = math.ceil(e)
            window.draw_rectangle(gc[c[0]], 1,  x0, s,  x1, e-s)

    def _sync_scroll(self, which_is_master):
        assert(which_is_master == 0 or which_is_master == 1)
        # only allow one scrollbar to be here at a time
        if not hasattr(self,"_sync_scroll_lock"):
            self._sync_scroll_lock = 0
        # maybe cache some of these?
        if not self._sync_scroll_lock:
            self._sync_scroll_lock = 1
            syncpoint = 0.5
            madj = self.scrolledwindow0.get_vadjustment()
            oadj = self.scrolledwindow1.get_vadjustment()
            mtextlen = self._get_line_count(self.textview0)
            otextlen = self._get_line_count(self.textview1)
            if which_is_master == 1:
                madj,oadj = oadj,madj
                mtextlen,otextlen = otextlen,mtextlen
            other = not which_is_master

            mline = (madj.value + madj.page_size * syncpoint) / (madj.upper - madj.lower) * mtextlen
            mbegin,mend,obegin,oend = 0,0,0,0
            wbase = (1,3)[which_is_master]
            obase = (3,1)[which_is_master]
            for c in self.linediffs:
                if c[wbase] >= mline:
                    mend = c[wbase]
                    oend = c[obase]
                    break
                elif c[wbase+1] >= mline:
                    mbegin,mend = c[wbase:wbase+2]
                    obegin,oend = c[obase:obase+2]
                    break
                else:
                    mbegin = c[wbase+1]
                    obegin = c[obase+1]
            mfrac = (mline - mbegin ) / ((mend - mbegin) or 1)
            oline = (obegin + mfrac * (oend - obegin))
            opct =  oline / otextlen
            oval = oadj.lower + opct * (oadj.upper - oadj.lower) - oadj.page_size * syncpoint
            oval = min(oval, oadj.upper - oadj.page_size)
            oadj.set_value( oval )
            self.on_drawing2_expose_event(self.drawing2, None)
            #self.drawing2.queue_draw()
            self._sync_scroll_lock = 0

    def _ensure_fresh_tag_exists(self, name, buffer, properties):
        """tag exists in buffer and is not applied to any text"""
        table = buffer.get_tag_table()
        tag = table.lookup(name)
        if not tag:
            tag = buffer.create_tag(name)
            for prop,val in properties.items():
                tag.set_property(prop, val)
        else:
            buffer.remove_tag(tag, buffer.get_start_iter(), buffer.get_end_iter())
        return tag

gobject.type_register(FileDiff2)

################################################################################
#
# MeldApp
#
################################################################################
class BrowseFile2Dialog(gnomeglade.Dialog):
    def __init__(self, parentapp):
        gnomeglade.Dialog.__init__(self, "glade2/meld-app.glade", "browsefile2")
        self.parentapp = parentapp
    def on_response(self, dialog, arg):
        if arg==gtk.RESPONSE_OK:
            f0 = self.fileentry0.get_full_path(1) or ""
            f1 = self.fileentry1.get_full_path(1) or ""
            self.parentapp.append_filediff2( f0, f1 )
        self._widget.destroy() #TODO why ._widget?
   
################################################################################
#
# MeldApp
#
################################################################################
class MeldApp(gnomeglade.App):

    def __init__(self, files):
        gnomeglade.App.__init__(self, "Meld", "0.1", "glade2/meld-app.glade", "meldapp")
        if len(files)==2:
            self.append_filediff2( files[0],files[1] )

    #
    # global
    #
    def on_app_delete_event(self, *extra):
        self.quit()
    def on_help_about_activate(self, *extra):
        gtk.glade.XML("glade2/meld-app.glade","about").get_widget("about").show()
    def on_quit_activate(self, *extra):
        self.quit()
    #def on_button_press_event(self, text, event):
    #    if event.button==3:
    #        self.popup_menu.popup(None,None,None,3,0)
    #        return 1
    #    return 0

    #
    # current doc
    #
    def on_close_doc_activate(self, *extra):
        page = self.notebook.get_current_page()
        if page >= 0:
            self.notebook.remove_page(page)
    def on_new_doc_activate(self, *extra):
        BrowseFile2Dialog(self)
    def on_refresh_doc_clicked(self, *args):
        index = self.notebook.get_current_page()
        self.notebook.get_nth_page(index).get_data("pyobject").refresh() #TODO why not just w.refresh()

    def on_files_doc_loaded(self, component, file0, file1):
        l = self.notebook.get_tab_label( component._widget ) #TODO why ._widget?
        if l:
            f0 = os.path.basename(file0)
            f1 = os.path.basename(file1)
            l.set_text("%s\n%s" % (f0,f1))
    #
    # methods
    #
    def append_filediff2(self, file0, file1):
        l = gtk.Label("%s\n%s" % (file0,file1))
        d = FileDiff2()
        self.notebook.append_page( d._widget, l ) #TODO why ._widget?
        self.notebook.next_page()
        d.connect("files-loaded", self.on_files_doc_loaded)
        d.set_file(file0,0)
        d.set_file(file1,1)
        d.refresh()


################################################################################
#
# Main
#
################################################################################
def main():
    sys.stdout = sys.stderr
    if len(sys.argv)==3:
        args=sys.argv[1:3]
    else:
        args = []
    MeldApp(args).mainloop()

if __name__=="__main__":
    #import profile
    #profile.run("main()", "profile.meld")
    main()

