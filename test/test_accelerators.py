from gi.repository import Gtk

from meld.accelerators import VIEW_ACCELERATORS


def test_accelerator_parse():
    for accel_strings in VIEW_ACCELERATORS.values():
        if isinstance(accel_strings, str):
            accel_strings = [accel_strings]

        for accel_string in accel_strings:
            key, mods = Gtk.accelerator_parse(accel_string)
            assert key


def test_accelerator_duplication():
    accels = set()

    allowed_duplicates = {
        # Allowed because they're different copy actions across views
        Gtk.accelerator_parse("<Alt>Left"),
        Gtk.accelerator_parse("<Alt>Right"),
        # Allowed because they activate different popovers across views
        Gtk.accelerator_parse("F8"),
        # Allowed because they're different panel show/hide across views
        Gtk.accelerator_parse("F9"),
    }

    for accel_strings in VIEW_ACCELERATORS.values():
        if isinstance(accel_strings, str):
            accel_strings = [accel_strings]

        for accel_string in accel_strings:
            accel = Gtk.accelerator_parse(accel_string)

            if accel not in allowed_duplicates:
                assert (
                    accel not in accels
                ), f"Duplicate accelerator {accel_string}"
            accels.add(accel)
