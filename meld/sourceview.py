# Copyright (C) 2009 Vincent Legoll <vincent.legoll@gmail.com>
# Copyright (C) 2010-2011, 2013-2015 Kai Willadsen <kai.willadsen@gmail.com>
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

import logging
from enum import Enum

from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import GtkSource

from meld.meldbuffer import MeldBuffer
from meld.misc import colour_lookup_with_fallback, get_common_theme
from meld.settings import bind_settings, meldsettings, settings


log = logging.getLogger(__name__)


def get_custom_encoding_candidates():
    custom_candidates = []
    try:
        for charset in settings.get_value('detect-encodings'):
            encoding = GtkSource.Encoding.get_from_charset(charset)
            if not encoding:
                log.warning('Invalid charset "%s" skipped', charset)
                continue
            custom_candidates.append(encoding)
        if custom_candidates:
            custom_candidates.extend(
                GtkSource.Encoding.get_default_candidates())
    except AttributeError:
        # get_default_candidates() is only available in GtkSourceView 3.18
        # and we'd rather use their defaults than our old detect list.
        pass
    return custom_candidates


class LanguageManager:

    manager = GtkSource.LanguageManager()

    @classmethod
    def get_language_from_file(cls, gfile):
        try:
            info = gfile.query_info(
                Gio.FILE_ATTRIBUTE_STANDARD_CONTENT_TYPE, 0, None)
        except (GLib.GError, AttributeError):
            return None
        content_type = info.get_content_type()
        return cls.manager.guess_language(gfile.get_basename(), content_type)

    @classmethod
    def get_language_from_mime_type(cls, mime_type):
        content_type = Gio.content_type_from_mime_type(mime_type)
        return cls.manager.guess_language(None, content_type)


class TextviewLineAnimationType(Enum):
    fill = 'fill'
    stroke = 'stroke'


class TextviewLineAnimation:
    __slots__ = ("start_mark", "end_mark", "start_rgba", "end_rgba",
                 "start_time", "duration", "anim_type")

    def __init__(self, mark0, mark1, rgba0, rgba1, duration, anim_type):
        self.start_mark = mark0
        self.end_mark = mark1
        self.start_rgba = rgba0
        self.end_rgba = rgba1
        self.start_time = GLib.get_monotonic_time()
        self.duration = duration
        self.anim_type = anim_type


class MeldSourceView(GtkSource.View):

    __gtype_name__ = "MeldSourceView"

    __gsettings_bindings__ = (
        ('highlight-current-line', 'highlight-current-line-local'),
        ('indent-width', 'tab-width'),
        ('insert-spaces-instead-of-tabs', 'insert-spaces-instead-of-tabs'),
        ('draw-spaces', 'draw-spaces'),
        ('wrap-mode', 'wrap-mode'),
        ('show-line-numbers', 'show-line-numbers'),
    )

    # Named so as not to conflict with the GtkSourceView property
    highlight_current_line_local = GObject.Property(type=bool, default=False)

    def get_show_line_numbers(self):
        return self._show_line_numbers

    def set_show_line_numbers(self, show):
        if show == self._show_line_numbers:
            return

        if self.line_renderer:
            self.line_renderer.set_visible(show)

        self._show_line_numbers = bool(show)
        self.notify("show-line-numbers")

    show_line_numbers = GObject.Property(
        type=bool, default=False, getter=get_show_line_numbers,
        setter=set_show_line_numbers)

    replaced_entries = (
        # We replace the default GtkSourceView undo mechanism
        (Gdk.KEY_z, Gdk.ModifierType.CONTROL_MASK),
        (Gdk.KEY_z, Gdk.ModifierType.CONTROL_MASK |
            Gdk.ModifierType.SHIFT_MASK),

        # We replace the default line movement behaviour of Alt+Up/Down
        (Gdk.KEY_Up, Gdk.ModifierType.MOD1_MASK),
        (Gdk.KEY_KP_Up, Gdk.ModifierType.MOD1_MASK),
        (Gdk.KEY_KP_Up, Gdk.ModifierType.MOD1_MASK |
            Gdk.ModifierType.SHIFT_MASK),
        (Gdk.KEY_Down, Gdk.ModifierType.MOD1_MASK),
        (Gdk.KEY_KP_Down, Gdk.ModifierType.MOD1_MASK),
        (Gdk.KEY_KP_Down, Gdk.ModifierType.MOD1_MASK |
            Gdk.ModifierType.SHIFT_MASK),
        # ...and Alt+Left/Right
        (Gdk.KEY_Left, Gdk.ModifierType.MOD1_MASK),
        (Gdk.KEY_KP_Left, Gdk.ModifierType.MOD1_MASK),
        (Gdk.KEY_Right, Gdk.ModifierType.MOD1_MASK),
        (Gdk.KEY_KP_Right, Gdk.ModifierType.MOD1_MASK),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.drag_dest_add_uri_targets()

        binding_set = Gtk.binding_set_find('GtkSourceView')
        for key, modifiers in self.replaced_entries:
            Gtk.binding_entry_remove(binding_set, key, modifiers)
        self.anim_source_id = None
        self.animating_chunks = []
        self.syncpoints = []
        self._show_line_numbers = None

        buf = MeldBuffer()
        inline_tag = GtkSource.Tag.new("inline")
        inline_tag.props.draw_spaces = True
        buf.get_tag_table().add(inline_tag)
        buf.create_tag("dimmed")
        self.set_buffer(buf)

        meldsettings.connect('changed', self.on_setting_changed)

    def do_paste_clipboard(self, *args):
        # This is an awful hack to replace another awful hack. The idea
        # here is to sanitise the clipboard contents so that it doesn't
        # contain GtkTextTags, by requesting and setting plain text.

        def text_received_cb(clipboard, text, *user_data):
            # Manual encoding is required here, or the length will be
            # incorrect, and the API requires a UTF-8 bytestring.
            utf8_text = text.encode('utf-8')
            clipboard.set_text(text, len(utf8_text))
            self.get_buffer().paste_clipboard(
                clipboard, None, self.get_editable())

        clipboard = self.get_clipboard(Gdk.SELECTION_CLIPBOARD)
        clipboard.request_text(text_received_cb)

    def get_y_for_line_num(self, line):
        buf = self.get_buffer()
        it = buf.get_iter_at_line(line)
        y, h = self.get_line_yrange(it)
        if line >= buf.get_line_count():
            return y + h
        return y

    def get_line_num_for_y(self, y):
        return self.get_line_at_y(y)[0].get_line()

    def add_fading_highlight(
            self, mark0, mark1, colour_name, duration,
            anim_type=TextviewLineAnimationType.fill, starting_alpha=1.0):

        if not self.get_realized():
            return

        rgba0 = self.fill_colors[colour_name].copy()
        rgba1 = self.fill_colors[colour_name].copy()
        rgba0.alpha = starting_alpha
        rgba1.alpha = 0.0
        anim = TextviewLineAnimation(
            mark0, mark1, rgba0, rgba1, duration, anim_type)
        self.animating_chunks.append(anim)

    def on_setting_changed(self, settings, key):
        if key == 'font':
            self.override_font(meldsettings.font)
        elif key == 'style-scheme':
            self.highlight_color = colour_lookup_with_fallback(
                "meld:current-line-highlight", "background")
            self.syncpoint_color = colour_lookup_with_fallback(
                "meld:syncpoint-outline", "foreground")
            self.fill_colors, self.line_colors = get_common_theme()

            tag = self.get_buffer().get_tag_table().lookup("inline")
            tag.props.background_rgba = colour_lookup_with_fallback(
                "meld:inline", "background")
            tag = self.get_buffer().get_tag_table().lookup("dimmed")
            tag.props.foreground_rgba = colour_lookup_with_fallback(
                "meld:dimmed", "foreground")

    def do_realize(self):
        bind_settings(self)
        self.on_setting_changed(meldsettings, 'font')
        self.on_setting_changed(meldsettings, 'style-scheme')
        return GtkSource.View.do_realize(self)

    def do_draw_layer(self, layer, context):
        if layer != Gtk.TextViewLayer.BELOW_TEXT:
            return GtkSource.View.do_draw_layer(self, layer, context)

        context.save()
        context.set_line_width(1.0)

        _, clip = Gdk.cairo_get_clip_rectangle(context)
        bounds = (
            self.get_line_num_for_y(clip.y),
            self.get_line_num_for_y(clip.y + clip.height),
        )

        x = clip.x - 0.5
        width = clip.width + 1

        # Paint chunk backgrounds and outlines
        for change in self.chunk_iter(bounds):
            ypos0 = self.get_y_for_line_num(change[1])
            ypos1 = self.get_y_for_line_num(change[2])
            height = max(0, ypos1 - ypos0 - 1)

            context.rectangle(x, ypos0 + 0.5, width, height)
            if change[1] != change[2]:
                context.set_source_rgba(*self.fill_colors[change[0]])
                context.fill_preserve()
                if self.current_chunk_check(change):
                    highlight = self.fill_colors['current-chunk-highlight']
                    context.set_source_rgba(*highlight)
                    context.fill_preserve()

            context.set_source_rgba(*self.line_colors[change[0]])
            context.stroke()

        textbuffer = self.get_buffer()

        # Paint current line highlight
        if self.props.highlight_current_line_local and self.is_focus():
            it = textbuffer.get_iter_at_mark(textbuffer.get_insert())
            ypos, line_height = self.get_line_yrange(it)
            context.rectangle(x, ypos, width, line_height)
            context.set_source_rgba(*self.highlight_color)
            context.fill()

        # Draw syncpoint indicator lines
        for syncpoint in self.syncpoints:
            if syncpoint is None:
                continue
            syncline = textbuffer.get_iter_at_mark(syncpoint).get_line()
            if bounds[0] <= syncline <= bounds[1]:
                ypos = self.get_y_for_line_num(syncline)
                context.rectangle(x, ypos - 0.5, width, 1)
                context.set_source_rgba(*self.syncpoint_color)
                context.stroke()

        # Overdraw all animated chunks, and update animation states
        new_anim_chunks = []
        for c in self.animating_chunks:
            current_time = GLib.get_monotonic_time()
            percent = min(
                1.0, (current_time - c.start_time) / float(c.duration))
            rgba_pairs = zip(c.start_rgba, c.end_rgba)
            rgba = [s + (e - s) * percent for s, e in rgba_pairs]

            it = textbuffer.get_iter_at_mark(c.start_mark)
            ystart, _ = self.get_line_yrange(it)
            it = textbuffer.get_iter_at_mark(c.end_mark)
            yend, _ = self.get_line_yrange(it)
            if ystart == yend:
                ystart -= 1

            context.set_source_rgba(*rgba)
            context.rectangle(x, ystart, width, yend - ystart)
            if c.anim_type == TextviewLineAnimationType.stroke:
                context.stroke()
            else:
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

        return GtkSource.View.do_draw_layer(self, layer, context)


class CommitMessageSourceView(GtkSource.View):

    __gtype_name__ = "CommitMessageSourceView"

    __gsettings_bindings__ = (
        ('indent-width', 'tab-width'),
        ('insert-spaces-instead-of-tabs', 'insert-spaces-instead-of-tabs'),
        ('draw-spaces', 'draw-spaces'),
    )
