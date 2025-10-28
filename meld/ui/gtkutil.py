# Copyright (C) 2023 Kai Willadsen <kai.willadsen@gmail.com>
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

GTK_STYLE_CLASS_ERROR = "error"


def make_gdk_rgba(red: float, green: float, blue: float, alpha: float) -> Gdk.RGBA:
    rgba = Gdk.RGBA()
    rgba.red = red
    rgba.green = green
    rgba.blue = blue
    rgba.alpha = alpha
    return rgba


def format_gdk_rgba(rgba: Gdk.RGBA) -> str:
    return f"({rgba.red}, {rgba.green}, {rgba.blue}, {rgba.alpha})"


def alpha_tint(rgba: Gdk.RGBA, alpha: float) -> Gdk.RGBA:
    return make_gdk_rgba(
        red=alpha + rgba.red * (1.0 - alpha),
        green=alpha + rgba.green * (1.0 - alpha),
        blue=alpha + rgba.blue * (1.0 - alpha),
        alpha=alpha + rgba.alpha * (1.0 - alpha),
    )
