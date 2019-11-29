
import importlib.machinery
import importlib.util
import sys
from unittest import mock

import pytest


@pytest.fixture(autouse=True)
def default_icon_theme():
    # Our tests need to run on a system with no default display, so all
    # our display-specific get_default() stuff will break.

    from gi.repository import Gtk
    with mock.patch(
            'gi.repository.Gtk.IconTheme.get_default',
            mock.Mock(spec=Gtk.IconTheme.get_default)):
        yield


@pytest.fixture(autouse=True)
def template_resources():
    import gi  # noqa: F401
    with mock.patch(
            'gi._gtktemplate.validate_resource_path',
            mock.Mock(return_value=True)):
        yield


def import_meld_conf():
    loader = importlib.machinery.SourceFileLoader(
        'meld.conf', './meld/conf.py.in')
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)

    import meld
    meld.conf = mod
    sys.modules['meld.conf'] = mod


import_meld_conf()
