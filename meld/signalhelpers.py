from collections.abc import Iterator
from contextlib import contextmanager

from gi.repository import GObject


@contextmanager
def block_signal_handlers(
    instance: GObject.Object,
    *,
    signal_id: int = 0,
    detail: int = 0,
    closure: GObject.Closure | None = None,
) -> Iterator[None]:
    """Block matching instance signal handlers"""

    mask = GObject.SignalMatchType(0)
    if signal_id:
        mask |= GObject.SignalMatchType.ID
    if detail:
        mask |= GObject.SignalMatchType.DETAIL
    if closure:
        mask |= GObject.SignalMatchType.CLOSURE

    match_args = (instance, mask, signal_id, detail, closure, 0, 0)
    GObject.signal_handlers_block_matched(*match_args)
    try:
        yield
    finally:
        GObject.signal_handlers_unblock_matched(*match_args)
