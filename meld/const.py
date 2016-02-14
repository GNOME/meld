
from gi.repository import GtkSource

from meld.conf import _

# Chunk action mode, set by filediff and used in gutterrendererchunk
MODE_REPLACE = 0
MODE_DELETE = 1
MODE_INSERT = 2

NEWLINES = {
    GtkSource.NewlineType.LF: ('\n', _("UNIX (LF)")),
    GtkSource.NewlineType.CR_LF: ('\r\n', _("DOS/Windows (CR-LF)")),
    GtkSource.NewlineType.CR: ('\r', _("Mac OS (CR)")),
}
