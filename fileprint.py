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

import gnomeprint
import gobject
import pango
import misc
import math
import misc


def do_print(job, texts, chunks, label_text):
    options = misc.struct(landscape=True, color=False)
    config = job.get_config()
    context = gnomeprint.pango_create_context(
        gnomeprint.pango_get_default_font_map())
    #if options.landscape:
   #     config.set( gnomeprint.KEY_PAPER_ORIENTATION, "R90" )

    def units(key):
        v,u = config.get_length( key )
        return v * u.unittobase
    paper_width = units( gnomeprint.KEY_PAPER_WIDTH )
    paper_height = units( gnomeprint.KEY_PAPER_HEIGHT ) 
    transform_rotate = 0
    transform_ytranslate = 0
    if options.landscape:
        transform_rotate = 90
        transform_ytranslate = -paper_width
        paper_width, paper_height = paper_height, paper_width

    #job.print_to_file("output_01.ps")

    num_texts = len(texts)
    line_numbers = [1 for i in range(num_texts)]
    def setup_line_numbers():
        layout = pango.Layout(context)
        line_num_cols = int( math.log( max( [len(t) for t in texts] ), 10) ) + 1
        line_num_format = "%%%ii" % line_num_cols
        layout.set_text("0"*(line_num_cols+1))
        line_num_width = layout.get_extents()[1][2] / pango.SCALE
        return line_num_format, line_num_width
    line_num_format, line_num_width = setup_line_numbers()

    column_width = paper_width // num_texts
    usable_width = column_width - line_num_width

    layouts = [ pango.Layout(context) for i in range(num_texts) ]
    for l in layouts:
        l.set_font_description( pango.FontDescription("Mono 10") )
        l.set_wrap(pango.WRAP_WORD_CHAR)
        l.set_width( int(usable_width*pango.SCALE) )
        print dir(l)

    def mul_tuple(s, t):
        return tuple( [ s*i for i in t ] )

    reversemap = {
        "replace":"replace",
         "insert":"delete",
         "delete":"insert",
         "conflict":"conflict",
         "equal":"equal"}

    gpc = job.get_context()

    def draw_chunks(chunks, state):
        lo_ranges = [ 0, 0, 0 ]
        hi_ranges = [ 0, 0, 0 ]
        chunk_type = [None, None, None]
        if chunks[0]:
            c = chunks[0]
            chunk_type[0] = reversemap[c[0]]
            chunk_type[1] = c[0]
            lo_ranges[0], hi_ranges[0] = c[3], c[4]
            lo_ranges[1], hi_ranges[1] = c[1], c[2]
        if chunks[1]:
            c = chunks[1]
            chunk_type[1] = c[0]
            chunk_type[2] = reversemap[c[0]]
            lo_ranges[1], hi_ranges[1] = c[3], c[4]
            lo_ranges[2], hi_ranges[2] = c[1], c[2]

        while 1 in [ l<h for l,h in zip(lo_ranges, hi_ranges) ]:
            for i,layout in enumerate(layouts):
                if lo_ranges[i] < hi_ranges[i]:
                    layout.set_markup( misc.escape( texts[i][lo_ranges[i]]) )
                else:
                    layout.set_markup("")
            logicals = [l.get_extents()[1] for l in layouts]
            rects = [ mul_tuple(1.0/pango.SCALE, l) for l in logicals ]
            ystep = max( [r[3] for r in rects] )
            if state.cury - ystep < 0:
                state.curpage += 1
                gpc.showpage()
                gpc.beginpage(str(state.curpage))
                gpc.rotate(transform_rotate)
                gpc.translate(0,transform_ytranslate)
                state.cury = paper_height
                yield "[%s] : page %i" % (label_text, state.curpage)

            for i in range(num_texts):
                lay = layouts[i]
                if lo_ranges[i] < hi_ranges[i]:
                    if options.color:
                        if chunk_type[i] == "delete":
                            gpc.setrgbcolor(193.0/255,255.0/255,193.0/255)
                            gpc.rect_filled( i*column_width, state.cury-rects[i][3],
                                column_width, rects[i][3] )
                        elif chunk_type[i] == "replace":
                            gpc.setrgbcolor(221.0/255, 238.0/255, 255.0/255)
                            gpc.rect_filled( i*column_width, state.cury-rects[i][3],
                                column_width, rects[i][3] )
                    if chunk_type[i] == "equal":
                        gpc.setrgbcolor(.5,.5,.5)
                    else:
                        gpc.setrgbcolor(0,0,0)

                    gpc.moveto(i*column_width+line_num_width,state.cury)
                    gpc.pango_layout(layouts[i])

                    if line_num_format:
                        gpc.setrgbcolor(0,0,0)
                        gpc.moveto(i*column_width,state.cury)
                        layouts[i].set_text(line_num_format % (1+lo_ranges[i]))
                        gpc.pango_layout(layouts[i])
                    lo_ranges[i] += 1
            state.cury -= ystep
        state.line_nums = hi_ranges

    state = misc.struct(curpage=0, cury=paper_height, line_nums=[0,0,0])
    gpc.beginpage(str(state.curpage))
    gpc.rotate(transform_rotate)
    gpc.translate(0,transform_ytranslate)

    for chunk in chunks:
        cbegin = [0,0,0]
        if chunk[0]:
            cbegin[0] = chunk[0][3]
            cbegin[1] = chunk[0][1]
        if chunk[1]:
            cbegin[1] = chunk[1][1]
            cbegin[2] = chunk[1][3]
        eq_chunks = [None,None]
        if state.line_nums[0] < cbegin[0]:
            eq_chunks[0] = "equal", state.line_nums[1], cbegin[1], state.line_nums[0], cbegin[0]
        if state.line_nums[2] < cbegin[2]:
            eq_chunks[1] = "equal", state.line_nums[1], cbegin[1], state.line_nums[2], cbegin[2]
        if eq_chunks.count(None) != 2:
            for i in draw_chunks(eq_chunks,state):
                yield i
        for i in draw_chunks(chunk,state):
            yield i
    eq_chunks = [None,None]
    if state.line_nums[0] < len(texts[0]):
        eq_chunks[0] = "equal", state.line_nums[1], len(texts[1]), state.line_nums[0], len(texts[0])
    if len(texts)==3 and state.line_nums[2] < len(texts[2]):
        eq_chunks[1] = "equal", state.line_nums[1], len(texts[1]), state.line_nums[2], len(texts[2])
    if eq_chunks.count(None) != 2:
        for i in draw_chunks(eq_chunks,state):
            yield i

    gpc.showpage()
    job.close()
    yield "[%s] : Sending to printer" % label_text
    #job.print_()

