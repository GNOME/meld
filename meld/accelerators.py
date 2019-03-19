
from gi.repository import Gtk


def register_accels(app: Gtk.Application):
    view_accels = (
        ('app.quit', '<Primary>Q'),
        ('view.find', '<Primary>F'),
        ('view.find-next', '<Primary>G'),
        ('view.find-previous', '<Primary><Shift>G'),
        ('view.find-replace', '<Primary>H'),
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
        ('win.close', '<Primary>W'),
        ('win.new-tab', '<Primary>N'),
        ('win.stop', 'Escape'),
        # File comparison actions
        ('view.file-previous-conflict', '<Primary>I'),
        ('view.file-next-conflict', '<Primary>K'),
        ('view.file-push-left', '<Alt>Left'),
        ('view.file-push-right', '<Alt>Right'),
        ('view.file-pull-left', '<Alt><shift>Right'),
        ('view.file-pull-right', '<Alt><shift>Left'),
        ('view.file-copy-left-up', '<Alt>bracketleft'),
        ('view.file-copy-right-up', '<Alt>bracketright'),
        ('view.file-copy-left-down', '<Alt>semicolon'),
        ('view.file-copy-right-down', '<Alt>quoteright'),
        ('view.file-delete', ('<Alt>Delete', '<Alt>KP_Delete')),
        ('view.show-sourcemap', 'F9'),
        # Folder comparison actions
        ('view.folder-compare', 'Return'),
        ('view.folder-copy-left', '<Alt>Left'),
        ('view.folder-copy-right', '<Alt>Right'),
        ('view.folder-delete', 'Delete'),
        # Version control actions
        ('view.vc-commit', '<Primary>M'),
        ('view.vc-console-visible', 'F9'),
    )
    for (name, accel) in view_accels:
        accel = accel if isinstance(accel, tuple) else (accel,)
        app.set_accels_for_action(name, accel)
