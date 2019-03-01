
from gi.repository import Gtk


def register_accels(app: Gtk.Application):
    view_accels = (
        ('view.find', '<Primary>F'),
        ('view.find-next', '<Primary>G'),
        ('view.find-previous', '<Primary><Shift>G'),
        ('view.find-replace', '<Primary>H'),
        ('view.folder-compare', 'Return'),
        ('view.folder-copy-left', '<Alt>Left'),
        ('view.folder-copy-right', '<Alt>Right'),
        ('view.folder-delete', 'Delete'),
        ('view.go-to-line', '<Primary>I'),
        ('view.next-change', ('<Alt>Down', '<Alt>KP_Down', '<Primary>D')),
        ('view.next-pane', '<Alt>Page_Down'),
        ('view.previous-change', ('<Alt>Up', '<Alt>KP_Up', '<Primary>E')),
        ('view.previous-pane', '<Alt>Page_Up'),
        ('view.redo', '<Primary><Shift>Z'),
        ('view.refresh', ('<control>R', 'F5')),
        ('view.save', '<Primary>S'),
        ('view.save-all', '<Primary><Shift>L'),
        ('view.save-as', '<Primary><Shift>S'),
        ('view.undo', '<Primary>Z'),
        ('view.vc-commit', '<Primary>M'),
        ('view.vc-console-visible', 'F9'),
        ('win.close', '<Primary>W'),
        ('win.new-tab', '<Primary>N'),
        ('win.stop', 'Escape'),
    )
    for (name, accel) in view_accels:
        accel = accel if isinstance(accel, tuple) else (accel,)
        app.set_accels_for_action(name, accel)
