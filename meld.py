#! /usr/bin/env python2.2

import os
import re
import stat
import time
import sys
import string
import difflib
import math
sys.path.append("/home/stephen/gnome/head/INSTALL/lib/python2.2/site-packages")

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


################################################################################
#
# FileDiff2
#
################################################################################
class FileDiff2(gnomeglade.Component):
    def __init__(self, notebooklabel, application):
        gnomeglade.Component.__init__(self, "glade2/filediff2.glade", "filediff2")
        self.notebooklabel = notebooklabel
        self.application = application
        sizegroup = gtk.SizeGroup(1)
        sizegroup.add_widget(self.textview0)
        sizegroup.add_widget(self.textview1)
        self.scrolledwindow0.get_vadjustment().connect("value-changed", lambda adj: self._sync_scroll(0) )
        self.scrolledwindow1.get_vadjustment().connect("value-changed", lambda adj: self._sync_scroll(1) )
        self.prefs = struct(deleted_color="#ebffeb", changed_color="#ebebff")
        self.prefs = struct(deleted_color="#ffaaaa", changed_color="#aaffaa")
        self.linediffs = []

    def set_file(self, filename, which):
        view = (self.textview0, self.textview1)[which]
        try:
            text = open(filename).read()
        except IOError, e:
            print e
            text = ""
        view.get_buffer().set_text( text )
        entry = (self.fileentry0, self.fileentry1)[which]
        entry.set_filename(filename)
        f0 = os.path.basename( self.fileentry0.get_full_path(0) or "None" )
        f1 = os.path.basename( self.fileentry1.get_full_path(0) or "None" )
        self.notebooklabel.set_text( "%s\n%s" % (f0,f1) )

    def on_fileentry0_activate(self, entry):
        self.set_file( entry.get_full_path(0), 0)
    def on_fileentry1_activate(self, entry):
        self.set_file( entry.get_full_path(0), 1)
    def on_drawing0_expose_event(self, area, event):
        self._draw_diff_map(self.drawing0, self.textview0, 1, "delete")
    def on_drawing1_expose_event(self, area, event):
        self._draw_diff_map(self.drawing1, self.textview1, 3, "insert")
    def on_drawing2_expose_event(self, area, event):
        window = area.window
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

        #im = gtk.Image()
        #im.set_from_file("/usr/share/pixmaps/tcd/ff.xpm")
        #imff = im.get_pixbuf()
        #im.set_from_file("/usr/share/pixmaps/tcd/rw.xpm")
        #imrw = im.get_pixbuf()

        for c in filter( lambda x: x[0]!="equal", self.linediffs):
            f0,f1 = map( lambda l: l * pixels_per_line - madj.value, c[1:3] )
            t0,t1 = map( lambda l: l * pixels_per_line - oadj.value, c[3:5] )
            if f0==f1: f0 -= 3; f1 += 1
            if t0==t1: t0 -= 3; t1 += 1
            bias = lambda x,g: math.pow(x, math.log(g) / math.log(0.5))
            def gain(t,g):
                if t<0.5:
                    return bias(2*t,1-g)/2.0
                else:
                    return (2-bias(2-2*t,1-g))/2.0
            f = lambda x: gain( x, 0.85)
            n = 10.0
            points0 = []
            points1 = [] 
            for t in map(lambda x: x/n, range(n+1)):
                points0.append( (    t*wtotal, (1-f(t))*f0 + f(t)*t0 ) )
                points1.append( ((1-t)*wtotal, f(t)*f1 + (1-f(t))*t1 ) )

            points = points0 + points1 + [points0[0]]
            window.draw_polygon(gcfg, 1, points)
            window.draw_lines(style.text_gc[0], points0  )
            window.draw_lines(style.text_gc[0], points1  )

            #impos = [wtotal/2, (points0[0][1] + points0[-1][1] + points1[0][1] + points1[-1][1])/4 ]
            #impos[0] -= imff.get_width()/2
            #impos[1] -= imff.get_height()/2
            #if c[0]=="insert":
            #    imff.render_to_drawable( window, gcfg, 0,0, impos[0],impos[1], -1,-1, 0,0,0)
            #else:
            #    imrw.render_to_drawable( window, gcfg, 0,0, impos[0],impos[1], -1,-1, 0,0,0)
        window.draw_line(style.text_gc[0], .25*wtotal,  0.5*htotal,.75*wtotal, 0.5*htotal)
        
    def refresh(self, *args):
        b0 = self.textview0.get_buffer()
        t0 = b0.get_text(b0.get_start_iter(), b0.get_end_iter(), 0)
        b1 = self.textview1.get_buffer()
        t1 = b1.get_text(b1.get_start_iter(), b1.get_end_iter(), 0)
        self.linediffs = difflib.SequenceMatcher(None, t0.split("\n"), t1.split("\n")).get_opcodes()
        self._highlight_buffer(0)
        self._highlight_buffer(1)
        self.on_drawing2_expose_event(self.drawing2, None)

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

    def _draw_diff_map(self, drawing, text, base, ignore):
        XXXX = 14 # height of arrow button on scrollbar - how do we get that?
        offset = self.fileentry0.get_allocation()[3] + XXXX
        hperline = float( text.get_allocation()[3] - 2*XXXX) / self._get_line_count(text)
        scaleit = lambda x,s=hperline,o=offset: x*s+o
        x0 = 3
        x1 = drawing.get_allocation()[2] - 2*x0

        window = drawing.window
        style = drawing.get_style()
        gc = { "insert":style.light_gc[0],
               "delete":style.light_gc[0],
               "replace":style.dark_gc[0] }
        for c in filter(lambda x: x[0]!='equal' and x[0]!=ignore, self.linediffs):
            (s,e) = c[base:base+2]
            e += s==e
            (s,e) = map( scaleit, (s,e+1) )
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
            oadj.set_value( oval )
            self.on_drawing2_expose_event(self.drawing2, None)
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


################################################################################
#
# MeldApp
#
################################################################################
class MeldApp(gnomeglade.App):

    def __init__(self, files):
        gnomeglade.App.__init__(self, "Meld", "0.1", "glade2/meld-app.glade", "meldapp")
        if len(files)==2:
            l = gtk.Label("%s\n%s" % (files[0],files[1]))
            w = FileDiff2(l,self)
            self.notebook.append_page( w._widget, l )
            w.set_file(files[0],0)
            w.set_file(files[1],1)
            w.refresh()

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
        l = gtk.Label("%s\n%s" % (None,None))
        w = FileDiff2(l,self)
        self.notebook.append_page( w._widget, l )
    def on_refresh_doc_clicked(self, *extra):
        self.notebook.get_nth_page( self.notebook.get_current_page() ).refresh()
    def on_refresh_doc_clicked(self, *args):
        index = self.notebook.get_current_page()
        self.notebook.get_nth_page(index).get_data("pyobject").refresh()


################################################################################
#
# Main
#
################################################################################
if __name__=="__main__":
    sys.stdout = sys.stderr
    if len(sys.argv)==3:
        args=sys.argv[1:3]
    else:
        args = []
    MeldApp(args).mainloop()

