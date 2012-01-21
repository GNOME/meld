
import os

__package__ = "meld"
__version__ = "1.7.5"

DATADIR = None
LOCALEDIR = None


def uninstalled():
    global DATADIR, LOCALEDIR
    melddir = os.path.abspath(os.path.join(
        os.path.dirname(os.path.realpath(__file__)), ".."))

    DATADIR = DATADIR or os.path.join(melddir, "data")
    LOCALEDIR = LOCALEDIR or os.path.join(melddir, "build", "mo")
