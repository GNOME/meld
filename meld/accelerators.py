
from gi.repository import Gtk


def register_accels(app: Gtk.Application):
    view_accels = (
        ('view.folder-compare', 'Return'),
        ('view.folder-copy-left', '<Alt>Left'),
        ('view.folder-copy-right', '<Alt>Right'),
        ('view.folder-delete', 'Delete'),
        ("view.next-change", ("<Alt>Down", "<Alt>KP_Down", "<Primary>D")),
        ("view.previous-change", ("<Alt>Up", "<Alt>KP_Up", "<Primary>E")),
        ('view.redo', '<Primary><Shift>Z'),
        ("view.refresh", ("<control>R", "F5")),
        ('view.save', '<Primary>S'),
        ('view.save-all', '<Primary><Shift>L'),
        ('view.save-as', '<Primary><Shift>S'),
        ('view.undo', '<Primary>Z'),
        ('view.vc-commit', '<Primary>M'),
        ('view.vc-console-visible', 'F9'),
        ('win.close', '<Primary>W'),
        ("win.stop", "Escape"),
    )
    for (name, accel) in view_accels:
        accel = accel if isinstance(accel, tuple) else (accel,)
        app.set_accels_for_action(name, accel)