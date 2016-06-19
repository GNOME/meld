
import os
import sys

__package__ = "meld"
__version__ = "3.16.2"

# START; these paths are clobbered on install by meld.build_helpers
DATADIR = os.path.join(sys.prefix, "share", "meld")
LOCALEDIR = os.path.join(sys.prefix, "share", "locale")
# END
UNINSTALLED = False

# Installed from main script
_ = lambda x: x
ngettext = lambda x, *args: x


def frozen():
    global DATADIR, LOCALEDIR

    melddir = os.path.dirname(sys.executable)

    DATADIR = os.path.join(melddir, "share", "meld")
    LOCALEDIR = os.path.join(melddir, "share", "mo")

    # This first bit should be unnecessary, but some things (GTK icon theme
    # location, GSettings schema location) don't fall back correctly.
    data_dir = os.environ.get('XDG_DATA_DIRS', "/usr/local/share/:/usr/share/")
    data_dir = ":".join((melddir, data_dir))
    os.environ['XDG_DATA_DIRS'] = data_dir


def uninstalled():
    global DATADIR, LOCALEDIR, UNINSTALLED
    melddir = os.path.abspath(os.path.join(
        os.path.dirname(os.path.realpath(__file__)), ".."))

    DATADIR = os.path.join(melddir, "data")
    LOCALEDIR = os.path.join(melddir, "build", "mo")
    UNINSTALLED = True

    # This first bit should be unnecessary, but some things (GTK icon theme
    # location, GSettings schema location) don't fall back correctly.
    data_dir = os.environ.get('XDG_DATA_DIRS', "/usr/local/share/:/usr/share/")
    data_dir = ":".join((melddir, data_dir))
    os.environ['XDG_DATA_DIRS'] = data_dir
