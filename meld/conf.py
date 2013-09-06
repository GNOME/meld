
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

    # This first bit should be unnecessary, but some things (GTK icon theme
    # location, GSettings schema location) don't fall back correctly.
    data_dir = os.environ.get('XDG_DATA_DIRS', "/usr/local/share/:/usr/share/")
    data_dir = ":".join((melddir, data_dir))
    os.environ['XDG_DATA_DIRS'] = data_dir
