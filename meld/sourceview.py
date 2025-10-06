# Copyright (C) 2009 Vincent Legoll <vincent.legoll@gmail.com>
# Copyright (C) 2010-2011, 2013-2019 Kai Willadsen <kai.willadsen@gmail.com>
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

from gi.repository import Gdk, Gio, GLib, GObject, Graphene, Gsk, Gtk, GtkSource, Pango

from meld.meldbuffer import MeldBuffer
from meld.settings import bind_settings, get_meld_settings, settings
from meld.style import colour_lookup_with_fallback, get_common_theme

log = logging.getLogger(__name__)

CONTROL_MASK = Gdk.ModifierType.CONTROL_MASK
SHIFT_MASK = Gdk.ModifierType.SHIFT_MASK
ALT_MASK = Gdk.ModifierType.ALT_MASK


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


class SourceViewHelperMixin:

    def get_y_for_line_num(self, line):
        buf = self.get_buffer()
        _found, it = buf.get_iter_at_line(line)
        y, h = self.get_line_yrange(it)
        if line >= buf.get_line_count():
            return y + h
        return y

    def get_line_num_for_y(self, y):
        return self.get_line_at_y(y)[0].get_line()


class MeldSourceView(GtkSource.View, SourceViewHelperMixin):

    __gtype_name__ = "MeldSourceView"

    __gsettings_bindings_view__ = (
        ('highlight-current-line', 'highlight-current-line-local'),
        ('indent-width', 'tab-width'),
        ('insert-spaces-instead-of-tabs', 'insert-spaces-instead-of-tabs'),
        ('enable-space-drawer', 'draw-spaces-bool'),
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

        if getattr(self, 'line_renderer', None):
            self.line_renderer.set_visible(show)

        self._show_line_numbers = bool(show)
        self.notify("show-line-numbers")

    show_line_numbers = GObject.Property(
        type=bool, default=False, getter=get_show_line_numbers,
        setter=set_show_line_numbers)

    wrap_mode_bool = GObject.Property(
        type=bool, default=False,
        nick="Wrap mode (Boolean version)",
        blurb=(
            "Mirror of the wrap-mode GtkTextView property, reduced to "
            "a single Boolean for UI ease-of-use."
        ),
    )

    draw_spaces_bool = GObject.Property(
        type=bool, default=False,
        nick="Draw spaces (Boolean version)",
        blurb=(
            "Mirror of the draw-spaces GtkSourceView property, "
            "reduced to a single Boolean for UI ease-of-use."
        ),
    )

    overscroll_num_lines = GObject.Property(
        type=int, default=5, minimum=0, maximum=100,
        nick="Overscroll line count",
        flags=(
            GObject.ParamFlags.READWRITE |
            GObject.ParamFlags.CONSTRUCT
        ),
    )

    @GObject.Signal(name="popup-menu")
    def popup_menu(self) -> None: ...

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # TODO4: We can't remove the Ctrl+PageUp/PageDown bindings on
        # GtkTextView, and can't override them here because we need them to be
        # handled by our notebook widget. It appears that this works in Builder
        # because AdwTabView captures these shortcuts in the propagation phase;
        # see meld.ui.notebook for why we want to switch to AdwTabView anyway.

        self.anim_source_id = None
        self.animating_chunks = []
        self.syncpoints = []
        self._show_line_numbers = None

        self.context_menu = None

        self.css_provider = Gtk.CssProvider()
        style_context = self.get_style_context()
        style_context.add_provider(self.css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        buf = MeldBuffer()
        inline_tag = GtkSource.Tag.new("inline")
        inline_tag.props.draw_spaces = True
        buf.get_tag_table().add(inline_tag)
        buf.create_tag("dimmed")
        self.set_buffer(buf)
        self.connect('notify::overscroll-num-lines', self.notify_overscroll)

    @property
    def line_height(self) -> int:
        if not getattr(self, '_approx_line_height', None):
            context = self.get_pango_context()
            layout = Pango.Layout(context)
            layout.set_text('X', -1)
            _width, self._approx_line_height = layout.get_pixel_size()

        return self._approx_line_height

    def notify_overscroll(self, view, param):
        self.props.bottom_margin = self.overscroll_num_lines * self.line_height

    def do_paste_clipboard(self, *args):
        # This is an awful hack to replace another awful hack. The idea
        # here is to sanitise the clipboard contents so that it doesn't
        # contain GtkTextTags, by requesting and setting plain text.

        def text_received_cb(clipboard, result, *user_data):
            text = clipboard.read_text_finish(result)
            # On clipboard failure, text will be None
            if not text:
                return

            clipboard.set(text)
            self.get_buffer().paste_clipboard(clipboard, None, self.get_editable())

        clipboard = self.get_clipboard()
        clipboard.read_text_async(None, text_received_cb)

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
            family, size = settings.get_font_css()
            style = f"* {{ {family} {size} }}"
            self.css_provider.load_from_string(style)
            self._approx_line_height = None
        elif key == 'style-scheme':
            self.highlight_color = colour_lookup_with_fallback(
                "meld:current-line-highlight", "background")
            self.syncpoint_color = colour_lookup_with_fallback(
                "meld:syncpoint-outline", "foreground")
            self.fill_colors, self.line_colors = get_common_theme()

            buf = self.get_buffer()
            buf.set_style_scheme(settings.style_scheme)

            tag = buf.get_tag_table().lookup("inline")
            tag.props.background_rgba = colour_lookup_with_fallback(
                "meld:inline", "background")
            tag = buf.get_tag_table().lookup("dimmed")
            tag.props.foreground_rgba = colour_lookup_with_fallback(
                "meld:dimmed", "foreground")

    def on_popup_menu(self, *args):
        # TODO4: This layer of indirection is only needed because of syncpoint
        # menu logic in FileDiff. If we manage to move that around, we could
        # move the FileDiff popup handling in on_textview_popup_menu and
        # on_textview_button_press_event to MeldSourceView.
        self.popup_menu.emit()

    def do_realize(self):
        bind_settings(self)

        def wrap_mode_from_bool(binding, from_value):
            if from_value:
                settings_mode = settings.get_enum('wrap-mode')
                if settings_mode == Gtk.WrapMode.NONE:
                    mode = Gtk.WrapMode.WORD
                else:
                    mode = settings_mode
            else:
                mode = Gtk.WrapMode.NONE
            return mode

        def wrap_mode_to_bool(binding, from_value):
            return bool(from_value)

        self.bind_property(
            'wrap-mode-bool', self, 'wrap-mode',
            GObject.BindingFlags.BIDIRECTIONAL,
            wrap_mode_from_bool,
            wrap_mode_to_bool,
        )
        self.wrap_mode_bool = wrap_mode_to_bool(None, self.props.wrap_mode)

        self.bind_property(
            'draw-spaces-bool', self.props.space_drawer, 'enable-matrix',
            GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE,
        )

        meld_settings = get_meld_settings()

        self.on_setting_changed(meld_settings, 'font')
        self.on_setting_changed(meld_settings, 'style-scheme')
        self.get_buffer().set_style_scheme(meld_settings.style_scheme)

        meld_settings.connect('changed', self.on_setting_changed)

        builder = Gtk.Builder.new_from_resource("/org/gnome/meld/ui/filediff-menus.ui")
        popup_menu_model = builder.get_object("filediff-context-menu")
        popup_menu = Gtk.PopoverMenu.new_from_model(popup_menu_model)
        popup_menu.set_parent(self)
        # Mimic the appearance of the standard GtkTextView context menu
        popup_menu.set_position(Gtk.PositionType.BOTTOM)
        popup_menu.set_has_arrow(False)
        popup_menu.set_halign(Gtk.Align.START)
        self.context_menu = popup_menu

        return GtkSource.View.do_realize(self)

    def do_unrealize(self):
        if self.anim_source_id:
            GLib.source_remove(self.anim_source_id)
        return GtkSource.View.do_unrealize(self)

    def do_snapshot_layer(self, layer, snapshot):
        if layer != Gtk.TextViewLayer.BELOW_TEXT:
            return GtkSource.View.do_snapshot_layer(self, layer, snapshot)

        snapshot.save()
        visible_rect = self.get_visible_rect()
        bounds = (
            self.get_line_num_for_y(visible_rect.y),
            self.get_line_num_for_y(visible_rect.y + visible_rect.height),
        )

        x = 0
        width = self.get_width() + 1

        rect = Graphene.Rect()
        rounded_rect = Gsk.RoundedRect()

        # Paint chunk backgrounds and outlines
        for change in self.chunk_iter(bounds):
            ypos0 = self.get_y_for_line_num(change[1])
            ypos1 = self.get_y_for_line_num(change[2])
            height = max(1, ypos1 - ypos0) + 1

            rect.init(x, ypos0, width, height)
            if change[1] != change[2]:
                color = self.fill_colors[change[0]]
                snapshot.append_color(color, rect)
                if self.current_chunk_check(change):
                    highlight = self.fill_colors['current-chunk-highlight']
                    snapshot.append_color(highlight, rect)

            color = self.line_colors[change[0]]
            rounded_rect.init_from_rect(rect, 0.0)
            snapshot.append_border(
                rounded_rect,
                [1.0, 0.0, 1.0, 0.0],
                [color, color, color, color],
            )

        textbuffer = self.get_buffer()

        # Check whether we're drawing past the last line in the buffer
        # (i.e., the overscroll) and draw a custom background if so.
        end_y, end_height = self.get_line_yrange(textbuffer.get_end_iter())
        end_y += end_height
        visible_bottom_margin = self.get_width() - end_y
        if visible_bottom_margin > 0:
            rect.init(x + 1, end_y, width - 1, visible_bottom_margin)
            color = self.fill_colors['overscroll']
            snapshot.append_color(color, rect)

        # Paint current line highlight
        if self.props.highlight_current_line_local:
            it = textbuffer.get_iter_at_mark(textbuffer.get_insert())
            ypos, line_height = self.get_line_yrange(it)
            rect.init(x, ypos, width, line_height)
            highlight = self.highlight_color
            snapshot.append_color(highlight, rect)

        # Draw syncpoint indicator lines
        for syncpoint in self.syncpoints:
            if syncpoint is None:
                continue
            syncline = textbuffer.get_iter_at_mark(syncpoint).get_line()
            if bounds[0] <= syncline <= bounds[1]:
                it = textbuffer.get_iter_at_mark(textbuffer.get_insert())
                ypos = self.get_y_for_line_num(syncline)
                ypos, line_height = self.get_line_yrange(it)
                rect.init(x, ypos - 0.5, width, 1)
                syncpoint = self.syncpoint_color
                rounded_rect.init_from_rect(rect, 0.0)
                snapshot.append_border(
                    rounded_rect,
                    [1.0, 1.0, 1.0, 1.0],
                    [syncpoint, syncpoint, syncpoint, syncpoint],
                )

        # Overdraw all animated chunks, and update animation states
        new_anim_chunks = []
        for c in self.animating_chunks:
            current_time = GLib.get_monotonic_time()
            percent = min(
                1.0, (current_time - c.start_time) / float(c.duration))

            def scale(start, end, percent):
                return start + (end - start) * percent

            # TODO4: Even though this runs fine, we don't get an actual
            # animated chunk, possibly because overdraw works differently
            # in GSK than in Cairo?
            rgba = Gdk.RGBA(
                scale(c.start_rgba.red, c.end_rgba.red, percent),
                scale(c.start_rgba.green, c.end_rgba.green, percent),
                scale(c.start_rgba.blue, c.end_rgba.blue, percent),
                scale(c.start_rgba.alpha, c.end_rgba.alpha, percent),
            )

            it = textbuffer.get_iter_at_mark(c.start_mark)
            ystart, _ = self.get_line_yrange(it)
            it = textbuffer.get_iter_at_mark(c.end_mark)
            yend, _ = self.get_line_yrange(it)
            if ystart == yend:
                ystart -= 1

            rect.init(x, ystart, width, (yend - ystart) + 1)
            if c.anim_type == TextviewLineAnimationType.stroke:
                rounded_rect.init_from_rect(rect, 0.0)
                snapshot.append_border(
                    rounded_rect,
                    [1.0, 1.0, 1.0, 1.0],
                    [rgba, rgba, rgba, rgba]
                )
            else:
                snapshot.append_color(rgba, rect)

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

        snapshot.restore()

        return GtkSource.View.do_snapshot_layer(self, layer, snapshot)


Gtk.WidgetClass.install_action(
    MeldSourceView,
    "menu.popup",
    None,
    MeldSourceView.on_popup_menu,
)


class CommitMessageSourceView(GtkSource.View):

    __gtype_name__ = "CommitMessageSourceView"

    __gsettings_bindings_view__ = (
        ('indent-width', 'tab-width'),
        ('insert-spaces-instead-of-tabs', 'insert-spaces-instead-of-tabs'),
        ('enable-space-drawer', 'enable-space-drawer'),
    )

    enable_space_drawer = GObject.Property(type=bool, default=False)

    def do_realize(self):
        bind_settings(self)

        self.bind_property(
            'enable-space-drawer', self.props.space_drawer, 'enable-matrix',
            GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE,
        )

        return GtkSource.View.do_realize(self)


class MeldSourceMap(GtkSource.Map, SourceViewHelperMixin):

    __gtype_name__ = "MeldSourceMap"

    compact_view = GObject.Property(
        type=bool,
        nick="Limit the view to a fixed width",
        default=False,
    )

    COMPACT_MODE_WIDTH = 40

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.connect('notify::compact-view', lambda *args: self.queue_resize())

    def do_draw_layer(self, layer, context):
        if layer != Gtk.TextViewLayer.BELOW_TEXT:
            return GtkSource.Map.do_draw_layer(self, layer, context)

        # Handle bad view assignments and partial initialisation
        parent_view = self.props.view
        if not hasattr(parent_view, 'chunk_iter'):
            return GtkSource.Map.do_draw_layer(self, layer, context)

        context.save()
        context.set_line_width(1.0)

        _, clip = Gdk.cairo_get_clip_rectangle(context)
        x = clip.x - 0.5
        width = clip.width + 1
        bounds = (
            self.get_line_num_for_y(clip.y),
            self.get_line_num_for_y(clip.y + clip.height),
        )

        # Paint chunk backgrounds
        for change in parent_view.chunk_iter(bounds):
            if change[1] == change[2]:
                # We don't have room to paint inserts in this widget
                continue

            ypos0 = self.get_y_for_line_num(change[1])
            ypos1 = self.get_y_for_line_num(change[2])
            height = max(0, ypos1 - ypos0 - 1)

            context.rectangle(x, ypos0 + 0.5, width, height)
            context.set_source_rgba(*parent_view.fill_colors[change[0]])
            context.fill()

        context.restore()

        return GtkSource.Map.do_draw_layer(self, layer, context)

    def do_get_preferred_width(self):
        if self.props.compact_view:
            return (self.COMPACT_MODE_WIDTH, self.COMPACT_MODE_WIDTH)
        else:
            return GtkSource.Map.do_get_preferred_width(self)
