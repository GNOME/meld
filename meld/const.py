
from meld.conf import _

# Chunk action mode, set by filediff and used in gutterrendererchunk
MODE_REPLACE = 0
MODE_DELETE = 1
MODE_INSERT = 2

NEWLINES = {
    '\n': _("UNIX (LF)"),
    '\r\n': _("DOS/Windows (CR-LF)"),
    '\r': _("Mac OS (CR)"),
}
