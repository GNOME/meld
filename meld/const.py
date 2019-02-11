
import enum

from gi.repository import GtkSource

from meld.conf import _


class ActionMode(enum.IntEnum):
    """Action mode for chunk change actions"""
    Replace = 0
    Delete = 1
    Insert = 2


class ChunkAction(enum.Enum):

    delete = 'delete'
    replace = 'replace'
    copy_down = 'copy_down'
    copy_up = 'copy_up'


NEWLINES = {
    GtkSource.NewlineType.LF: ('\n', _("UNIX (LF)")),
    GtkSource.NewlineType.CR_LF: ('\r\n', _("DOS/Windows (CR-LF)")),
    GtkSource.NewlineType.CR: ('\r', _("Mac OS (CR)")),
}
