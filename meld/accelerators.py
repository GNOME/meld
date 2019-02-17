
from gi.repository import Gtk


def register_accels(app: Gtk.Application):
    view_accels = (
        ("view.next-change", ("<Alt>Down", "<Alt>KP_Down", "<Primary>D")),
        ("view.previous-change", ("<Alt>Up", "<Alt>KP_Up", "<Primary>E")),
        ("view.refresh", ("<control>R", "F5")),
        ('view.save', '<Primary>S'),
        ('view.save-all', '<Primary><Shift>L'),
        ('view.save-as', '<Primary><Shift>S'),
        ('win.close', '<Primary>W'),
        ("win.stop", "Escape"),
    )
    for (name, accel) in view_accels:
        accel = accel if isinstance(accel, tuple) else (accel,)
        app.set_accels_for_action(name, accel)
