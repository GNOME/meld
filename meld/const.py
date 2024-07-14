
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


class FileComparisonMode(enum.Enum):
    AutoMerge = 'AutoMerge'
    Compare = 'Compare'


class FileLoadError(enum.IntEnum):
    LINE_TOO_LONG = 1


NEWLINES = {
    GtkSource.NewlineType.LF: ('\n', _("UNIX (LF)")),
    GtkSource.NewlineType.CR_LF: ('\r\n', _("DOS/Windows (CR-LF)")),
    GtkSource.NewlineType.CR: ('\r', _("Mac OS (CR)")),
}

FILE_FILTER_ACTION_FORMAT = 'folder-custom-filter-{}'
TEXT_FILTER_ACTION_FORMAT = 'text-custom-filter-{}'

#: Sentinel value for mtimes on files that don't exist.
MISSING_TIMESTAMP = -2147483648
