# Copyright (C) 2009 Vincent Legoll <vincent.legoll@gmail.com>
# Copyright (C) 2010-2011, 2013-2014 Kai Willadsen <kai.willadsen@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or (at
# your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import GtkSource

from meld.settings import bind_settings, settings


class LanguageManager(object):

    manager = GtkSource.LanguageManager()

    @classmethod
    def get_language_from_file(cls, filename):
        f = Gio.File.new_for_path(filename)
        try:
            info = f.query_info(Gio.FILE_ATTRIBUTE_STANDARD_CONTENT_TYPE,
                                0, None)
        except GLib.GError:
            return None
        content_type = info.get_content_type()
        return cls.manager.guess_language(filename, content_type)

    @classmethod
    def get_language_from_mime_type(cls, mime_type):
        content_type = Gio.content_type_from_mime_type(mime_type)
        return cls.manager.guess_language(None, content_type)


class TextviewLineAnimation(object):
    __slots__ = ("start_mark", "end_mark", "start_rgba", "end_rgba",
                 "start_time", "duration")

    def __init__(self, mark0, mark1, rgba0, rgba1, duration):
        self.start_mark = mark0
        self.end_mark = mark1
        self.start_rgba = rgba0
        self.end_rgba = rgba1
        self.start_time = GLib.get_monotonic_time()
        self.duration = duration


class MeldSourceView(GtkSource.View):

    __gtype_name__ = "MeldSourceView"

    __gsettings_bindings__ = (
        ('highlight-current-line', 'highlight-current-line-local'),
        ('indent-width', 'tab-width'),
        ('insert-spaces-instead-of-tabs', 'insert-spaces-instead-of-tabs'),
        ('draw-spaces', 'draw-spaces'),
        ('wrap-mode', 'wrap-mode'),
    )

    # Named so as not to conflict with the GtkSourceView property
    highlight_current_line_local = GObject.property(type=bool, default=False)

    replaced_entries = (
        # We replace the default GtkSourceView undo mechanism
        (Gdk.KEY_z, Gdk.ModifierType.CONTROL_MASK),
        (Gdk.KEY_z, Gdk.ModifierType.CONTROL_MASK |
            Gdk.ModifierType.SHIFT_MASK),

        # We replace the default line movement behaviour of Alt+Up/Down
        (Gdk.KEY_Up, Gdk.ModifierType.MOD1_MASK),
        (Gdk.KEY_KP_Up, Gdk.ModifierType.MOD1_MASK),
        (Gdk.KEY_Down, Gdk.ModifierType.MOD1_MASK),
        (Gdk.KEY_KP_Down, Gdk.ModifierType.MOD1_MASK),
        # ...and Alt+Left/Right
        (Gdk.KEY_Left, Gdk.ModifierType.MOD1_MASK),
        (Gdk.KEY_KP_Left, Gdk.ModifierType.MOD1_MASK),
        (Gdk.KEY_Right, Gdk.ModifierType.MOD1_MASK),
        (Gdk.KEY_KP_Right, Gdk.ModifierType.MOD1_MASK),
    )

    def __init__(self, *args, **kwargs):
        super(MeldSourceView, self).__init__(*args, **kwargs)
        binding_set = Gtk.binding_set_find('GtkSourceView')
        for key, modifiers in self.replaced_entries:
            Gtk.binding_entry_remove(binding_set, key, modifiers)
        self.anim_source_id = None
        self.animating_chunks = []
        self.syncpoints = []

    def late_bind(self):
        settings.bind(
            'show-line-numbers', self, 'show-line-numbers',
            Gio.SettingsBindFlags.DEFAULT)

    def get_y_for_line_num(self, line):
        buf = self.get_buffer()
        it = buf.get_iter_at_line(line)
        y, h = self.get_line_yrange(it)
        if line >= buf.get_line_count():
            return y + h - 1
        return y

    def get_line_num_for_y(self, y):
        return self.get_line_at_y(y)[0].get_line()

    def add_fading_highlight(self, mark0, mark1, colour_name, duration):
        rgba0 = self.fill_colors[colour_name].copy()
        rgba1 = self.fill_colors[colour_name].copy()
        rgba0.alpha = 1.0
        rgba1.alpha = 0.0
        anim = TextviewLineAnimation(mark0, mark1, rgba0, rgba1, duration)
        self.animating_chunks.append(anim)

    def do_realize(self):
        bind_settings(self)
        return GtkSource.View.do_realize(self)

    def do_style_updated(self, *args):
        GtkSource.View.do_style_updated(self)

        style = self.get_style_context()
        get_style_colour = lambda name: style.lookup_color(name)[1]

        self.highlight_color = get_style_colour("current-line-highlight")
        self.syncpoint_color = get_style_colour("syncpoint-outline")
        self.fill_colors = {
            "insert": get_style_colour("insert-bg"),
            "delete": get_style_colour("insert-bg"),
            "conflict": get_style_colour("conflict-bg"),
            "replace": get_style_colour("replace-bg"),
            "current-chunk-highlight": get_style_colour(
                "current-chunk-highlight"),
        }
        self.line_colors = {
            "insert": get_style_colour("insert-outline"),
            "delete": get_style_colour("insert-outline"),
            "conflict": get_style_colour("conflict-outline"),
            "replace": get_style_colour("replace-outline"),
        }

    def do_draw(self, context):

        windows = [
            self.get_window(window_type) for window_type in
            (Gtk.TextWindowType.TEXT, Gtk.TextWindowType.WIDGET)
            if self.get_window(window_type)]

        should_draw = [Gtk.cairo_should_draw_window(context, w) for w in windows]

        if not any(should_draw):
            return GtkSource.View.do_draw(self, context)

        context.save()

        visible = self.get_visible_rect()
        textbuffer = self.get_buffer()
        x, y = self.window_to_buffer_coords(
            Gtk.TextWindowType.WIDGET, 0, 0)
        view_allocation = self.get_allocation()
        bounds = (self.get_line_num_for_y(y),
                  self.get_line_num_for_y(y + view_allocation.height + 1))

        width, height = view_allocation.width, view_allocation.height
        context.set_line_width(1.0)

        # Paint chunk backgrounds and outlines
        for change in self.chunk_iter(bounds):
            ypos0 = self.get_y_for_line_num(change[1]) - visible.y
            ypos1 = self.get_y_for_line_num(change[2]) - visible.y

            context.rectangle(-0.5, ypos0 - 0.5, width + 1, ypos1 - ypos0)
            if change[1] != change[2]:
                context.set_source_rgba(*self.fill_colors[change[0]])
                context.fill_preserve()
                if self.current_chunk_check(change):
                    highlight = self.fill_colors['current-chunk-highlight']
                    context.set_source_rgba(*highlight)
                    context.fill_preserve()

            context.set_source_rgba(*self.line_colors[change[0]])
            context.stroke()

        # Paint current line highlight
        if self.props.highlight_current_line_local and self.is_focus():
            it = textbuffer.get_iter_at_mark(textbuffer.get_insert())
            ypos, line_height = self.get_line_yrange(it)
            context.save()
            context.rectangle(0, ypos - visible.y, width, line_height)
            context.clip()
            context.set_source_rgba(*self.highlight_color)
            context.paint_with_alpha(0.25)
            context.restore()

        # Draw syncpoint indicator lines
        for syncpoint in self.syncpoints:
            if syncpoint is None:
                continue
            syncline = textbuffer.get_iter_at_mark(syncpoint).get_line()
            if bounds[0] <= syncline <= bounds[1]:
                ypos = self.get_y_for_line_num(syncline) - visible.y
                context.rectangle(-0.5, ypos - 0.5, width + 1, 1)
                context.set_source_rgba(*self.syncpoint_color)
                context.stroke()

        # Overdraw all animated chunks, and update animation states
        new_anim_chunks = []
        for c in self.animating_chunks:
            current_time = GLib.get_monotonic_time()
            percent = min(1.0, (current_time - c.start_time) / float(c.duration))
            rgba_pairs = zip(c.start_rgba, c.end_rgba)
            rgba = [s + (e - s) * percent for s, e in rgba_pairs]

            it = textbuffer.get_iter_at_mark(c.start_mark)
            ystart, _ = self.get_line_yrange(it)
            it = textbuffer.get_iter_at_mark(c.end_mark)
            yend, _ = self.get_line_yrange(it)
            if ystart == yend:
                ystart -= 1

            context.set_source_rgba(*rgba)
            context.rectangle(0, ystart - visible.y, width, yend - ystart)
            context.fill()

            if current_time <= c.start_time + c.duration:
                new_anim_chunks.append(c)
            else:
                textbuffer.delete_mark(c.start_mark)
                textbuffer.delete_mark(c.end_mark)
        self.animating_chunks = new_anim_chunks

        if self.animating_chunks and self.anim_source_id is None:
            def anim_cb():
                self.queue_draw()
                return True
            # Using timeout_add interferes with recalculation of inline
            # highlighting; this mechanism could be improved.
            self.anim_source_id = GLib.idle_add(anim_cb)
        elif not self.animating_chunks and self.anim_source_id:
            GLib.source_remove(self.anim_source_id)
            self.anim_source_id = None

        context.restore()

        return GtkSource.View.do_draw(self, context)


class CommitMessageSourceView(GtkSource.View):

    __gtype_name__ = "CommitMessageSourceView"

    __gsettings_bindings__ = (
        ('indent-width', 'tab-width'),
        ('insert-spaces-instead-of-tabs', 'insert-spaces-instead-of-tabs'),
        ('draw-spaces', 'draw-spaces'),
    )
