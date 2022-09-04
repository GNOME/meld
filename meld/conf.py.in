
import os
import sys
from pathlib import Path

__package__ = "meld"
__version__ = "3.22.0"

APPLICATION_NAME = 'Meld'
APPLICATION_ID = 'org.gnome.Meld'
SETTINGS_SCHEMA_ID = 'org.gnome.meld'
RESOURCE_BASE = '/org/gnome/meld'

# START; these paths are clobbered on install by meld.build_helpers
DATADIR = Path(sys.prefix) / "share" / "meld"
LOCALEDIR = Path(sys.prefix) / "share" / "locale"
# END

CONFIGURED = '@configured@'
PROFILE = ''

if CONFIGURED == 'True':
    APPLICATION_ID = '@application_id@'
    DATADIR = '@pkgdatadir@'
    LOCALEDIR = '@localedir@'
    PROFILE = '@profile@'

# Flag enabling some workarounds if data dir isn't installed in standard prefix
DATADIR_IS_UNINSTALLED = False
PYTHON_REQUIREMENT_TUPLE = (3, 6)


# Installed from main script
def no_translation(gettext_string: str) -> str:
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

    melddir = Path(__file__).resolve().parent.parent

    DATADIR = melddir / "data"
    LOCALEDIR = melddir / "build" / "mo"
    DATADIR_IS_UNINSTALLED = True

    resource_path = melddir / "meld" / "resources"
    os.environ['G_RESOURCE_OVERLAYS'] = f'{RESOURCE_BASE}={resource_path}'
