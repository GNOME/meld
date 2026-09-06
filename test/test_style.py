import re

import pytest
from gi.repository import Gtk, Pango

import meld.style
from meld.style import update_font_zoom

BASE_FONT_SIZE = 11


@pytest.fixture(autouse=True)
def reset_zoom_state(mocker):
    mocker.patch.object(meld.style, "_font_size_offset", 0)


@pytest.fixture
def meld_settings(mocker):
    """Stub settings with a known font, capturing font-change notifications"""

    meld_settings = mocker.Mock()
    meld_settings.font = Pango.FontDescription(f"monospace {BASE_FONT_SIZE}")
    mocker.patch.object(meld.style, "get_meld_settings", return_value=meld_settings)
    return meld_settings


@pytest.fixture
def font_size(mocker, meld_settings):
    """Return the font size for our source views style contexts"""

    providers = []
    mocker.patch.object(
        Gtk.StyleContext,
        "add_provider_for_display",
        side_effect=lambda display, provider, priority: providers.append(provider),
    )

    def _font_size():
        meld.style.init_sourceview_style_context()
        css = providers[-1].to_string()
        return int(re.search(r"font-size:\s*(\d+)pt", css).group(1))

    return _font_size


def test_default_size_is_the_configured_font_size(font_size):
    assert font_size() == BASE_FONT_SIZE


def test_zoom_steps_by_a_point(font_size):
    sizes = []
    for _ in range(3):
        update_font_zoom(1)
        sizes.append(font_size())

    assert sizes == [BASE_FONT_SIZE + 1, BASE_FONT_SIZE + 2, BASE_FONT_SIZE + 3]

    for _ in range(3):
        update_font_zoom(-1)

    assert font_size() == BASE_FONT_SIZE


def test_zoom_reset(font_size):
    update_font_zoom(1)
    assert font_size() == BASE_FONT_SIZE + 1

    update_font_zoom(None)
    assert font_size() == BASE_FONT_SIZE


def test_zoom_emits_font_changed_correctly(meld_settings):
    # Check that zooming emits the changed signal
    update_font_zoom(1)
    meld_settings.emit.assert_called_once_with("changed", "font")

    # Resetting is a change here, but resetting again is not
    meld_settings.emit.reset_mock()
    update_font_zoom(None)
    update_font_zoom(None)
    meld_settings.emit.assert_called_once_with("changed", "font")

    # Neither is zooming out once we've hit the minimum font size
    update_font_zoom(-BASE_FONT_SIZE)
    meld_settings.emit.reset_mock()
    update_font_zoom(-1)
    meld_settings.emit.assert_not_called()
