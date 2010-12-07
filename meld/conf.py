
import os

PACKAGE = "meld" # "@PACKAGE"
VERSION = "1.7.3" # "@VERSION"
SHAREDIR = ( #SHAREDIR#
)
HELPDIR = ( #HELPDIR#
)
LOCALEDIR = ( #LOCALEDIR#
)

melddir = os.path.abspath(os.path.join(
              os.path.dirname(os.path.realpath(__file__)), ".."))

DATADIR = SHAREDIR or os.path.join(melddir, "data")
HELPDIR = HELPDIR or os.path.join(melddir, "help")
LOCALEDIR = LOCALEDIR or os.path.join(melddir, "po")

