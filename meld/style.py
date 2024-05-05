# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2009 Vincent Legoll <vincent.legoll@gmail.com>
# Copyright (C) 2012-2019 Kai Willadsen <kai.willadsen@gmail.com>
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

import enum
from typing import Mapping, Optional, Tuple

from gi.repository import Gdk, Gtk, GtkSource

from meld.conf import _


class MeldStyleScheme(enum.Enum):
    base = "meld-base"
    dark = "meld-dark"


style_scheme: Optional[GtkSource.StyleScheme] = None
base_style_scheme: Optional[GtkSource.StyleScheme] = None


def set_base_style_scheme(
    new_style_scheme: GtkSource.StyleScheme,
    prefer_dark: bool,
) -> GtkSource.StyleScheme:

    global base_style_scheme
    global style_scheme

    gtk_settings = Gtk.Settings.get_default()
    if gtk_settings:
        gtk_settings.props.gtk_application_prefer_dark_theme = prefer_dark

    style_scheme = new_style_scheme

    # Get our text background colour by checking the 'text' style of
    # the user's selected style scheme, falling back to the GTK+ theme
    # background if there is no style scheme background set.
    style = style_scheme.get_style('text') if style_scheme else None
    if style:
        background = style.props.background
        rgba = Gdk.RGBA()
        rgba.parse(background)
    else:
        # This case will only be hit for GtkSourceView style schemes
        # that don't set a text background, like the "Classic" scheme.
        from meld.sourceview import MeldSourceView
        stylecontext = MeldSourceView().get_style_context()
        background_set, rgba = (
            stylecontext.lookup_color('theme_bg_color'))
        if not background_set:
            rgba = Gdk.RGBA(1, 1, 1, 1)

    # This heuristic is absolutely dire. I made it up. There's
    # literally no basis to this.
    use_dark = (rgba.red + rgba.green + rgba.blue) < 1.0

    base_scheme_name = (
        MeldStyleScheme.dark if use_dark else MeldStyleScheme.base)

    manager = GtkSource.StyleSchemeManager.get_default()
    base_style_scheme = manager.get_scheme(base_scheme_name.value)
    base_schemes = (MeldStyleScheme.dark.value, MeldStyleScheme.base.value)
    if style_scheme and style_scheme.props.id in base_schemes:
        style_scheme = base_style_scheme

    return base_style_scheme


def colour_lookup_with_fallback(name: str, attribute: str) -> Gdk.RGBA:
    style = style_scheme.get_style(name) if style_scheme else None
    style_attr = getattr(style.props, attribute) if style else None
    if not style or not style_attr:
        try:
            style = base_style_scheme.get_style(name)
            style_attr = getattr(style.props, attribute)
        except AttributeError:
            pass

    if not style_attr:
        import sys
        style_detail = f'{name}-{attribute}'
        print(_(
            "Couldn’t find color scheme details for {}; "
            "this is a bad install").format(style_detail), file=sys.stderr)
        sys.exit(1)

    colour = Gdk.RGBA()
    colour.parse(style_attr)
    return colour


ColourMap = Mapping[str, Gdk.RGBA]


def get_common_theme() -> Tuple[ColourMap, ColourMap]:
    lookup = colour_lookup_with_fallback
    fill_colours = {
        "insert": lookup("meld:insert", "background"),
        "delete": lookup("meld:insert", "background"),
        "conflict": lookup("meld:conflict", "background"),
        "replace": lookup("meld:replace", "background"),
        "error": lookup("meld:error", "background"),
        "focus-highlight": lookup("meld:current-line-highlight", "foreground"),
        "current-chunk-highlight": lookup(
            "meld:current-chunk-highlight", "background"),
        "overscroll": lookup("meld:overscroll", "background"),
    }
    line_colours = {
        "insert": lookup("meld:insert", "line-background"),
        "delete": lookup("meld:insert", "line-background"),
        "conflict": lookup("meld:conflict", "line-background"),
        "replace": lookup("meld:replace", "line-background"),
        "error": lookup("meld:error", "line-background"),
    }
    return fill_colours, line_colours
