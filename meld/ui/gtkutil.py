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

from collections.abc import Iterator
from contextlib import contextmanager

from gi.repository import Gdk, GObject

GTK_STYLE_CLASS_ERROR = "error"

BIND_DEFAULT_CREATE = GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE


@contextmanager
def blocked_signal_handlers(
    instance: GObject.Object,
    *,
    signal_id: int = 0,
    detail: int = 0,
    closure: GObject.Closure | None = None,
    func: int = 0,
    data: int = 0,
) -> Iterator[None]:
    """Block matching signal handlers on `instance` for the duration of the block.

    The `GObject.SignalMatchType` mask is derived from whichever keyword
    arguments are supplied, so callers only pass the criteria they care
    about, e.g. ``blocked_signal_handlers(obj, signal_id=sid)``.
    """
    mask = GObject.SignalMatchType(0)
    if signal_id:
        mask |= GObject.SignalMatchType.ID
    if detail:
        mask |= GObject.SignalMatchType.DETAIL
    if closure is not None:
        mask |= GObject.SignalMatchType.CLOSURE
    if func:
        mask |= GObject.SignalMatchType.FUNC
    if data:
        mask |= GObject.SignalMatchType.DATA
    if not mask:
        raise ValueError("At least one match criterion must be provided")

    match_args = (instance, mask, signal_id, detail, closure, func, data)
    GObject.signal_handlers_block_matched(*match_args)
    try:
        yield
    finally:
        GObject.signal_handlers_unblock_matched(*match_args)


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
