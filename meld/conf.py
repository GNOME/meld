
import os
import sys

__package__ = "meld"
__version__ = "3.20.2"

APPLICATION_ID = "org.gnome.meld"

# START; these paths are clobbered on install by meld.build_helpers
DATADIR = os.path.join(sys.prefix, "share", "meld")
LOCALEDIR = os.path.join(sys.prefix, "share", "locale")
# END

# Flag enabling some workarounds if data dir isn't installed in standard prefix
DATADIR_IS_UNINSTALLED = False
PYTHON_REQUIREMENT_TUPLE = (3, 3)


# Installed from main script
def no_translation(gettext_string, *args):
    return gettext_string


_ = no_translation
ngettext = no_translation


def frozen():
    global DATADIR, LOCALEDIR, DATADIR_IS_UNINSTALLED

    melddir = os.path.dirname(sys.executable)

    DATADIR = os.path.join(melddir, "share", "meld")
    LOCALEDIR = os.path.join(melddir, "share", "mo")
    DATADIR_IS_UNINSTALLED = True


def uninstalled():
    global DATADIR, LOCALEDIR, DATADIR_IS_UNINSTALLED
    melddir = os.path.abspath(os.path.join(
        os.path.dirname(os.path.realpath(__file__)), ".."))

    DATADIR = os.path.join(melddir, "data")
    LOCALEDIR = os.path.join(melddir, "build", "mo")
    DATADIR_IS_UNINSTALLED = True


def ui_file(filename):
    return os.path.join(DATADIR, "ui", filename)
