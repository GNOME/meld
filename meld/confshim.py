from pathlib import Path
from typing import NamedTuple, Optional

from gi.repository import GLib


class MeldPaths(NamedTuple):
    user_plugins_dir: Path
    user_plugins_data_dir: Path
    system_plugins_dir: Path
    system_plugins_data_dir: Path


_meld_paths: Optional[MeldPaths] = None


def get_meld_paths() -> MeldPaths:
    global _meld_paths

    import meld
    from meld.conf import DATADIR  # type: ignore

    lib_path = Path(meld.__path__[0])
    user_path = Path(GLib.get_user_data_dir()) / "meld"

    if _meld_paths is None:
        _meld_paths = MeldPaths(
            user_plugins_dir=user_path / "plugins",
            user_plugins_data_dir=user_path / "plugins",
            system_plugins_dir=lib_path / "plugins",
            system_plugins_data_dir=DATADIR / "plugins",
        )

    return _meld_paths
