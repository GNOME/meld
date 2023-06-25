
from typing import Dict, Sequence, Union

from gi.repository import Gtk

VIEW_ACCELERATORS: Dict[str, Union[str, Sequence[str]]] = {
    'app.quit': '<Primary>Q',
    'app.help': 'F1',
    'app.preferences': '<Primary>comma',
    'view.find': '<Primary>F',
    'view.find-next': ('<Primary>G', 'F3'),
    'view.find-previous': ('<Primary><Shift>G', '<Shift>F3'),
    'view.find-replace': '<Primary>H',
    'view.go-to-line': '<Primary>I',
    # Overridden in CSS
    'view.next-change': ('<Alt>Down', '<Alt>KP_Down', '<Primary>D'),
    'view.next-pane': '<Alt>Page_Down',
    'view.open-external': '<Primary><Shift>O',
    # Overridden in CSS
    'view.previous-change': ('<Alt>Up', '<Alt>KP_Up', '<Primary>E'),
    'view.previous-pane': '<Alt>Page_Up',
    'view.redo': '<Primary><Shift>Z',
    'view.refresh': ('<control>R', 'F5'),
    'view.save': '<Primary>S',
    'view.save-all': '<Primary><Shift>L',
    'view.save-as': '<Primary><Shift>S',
    'view.undo': '<Primary>Z',
    'win.close': '<Primary>W',
    'win.gear-menu': 'F10',
    'win.fullscreen': 'F11',
    'win.new-tab': '<Primary>N',
    'win.stop': 'Escape',
    # Shared bindings for per-view filter menu buttons
    'view.vc-filter': 'F8',
    'view.folder-filter': 'F8',
    'view.text-filter': 'F8',
    # File comparison actions
    'view.file-previous-conflict': '<Primary>J',
    'view.file-next-conflict': '<Primary>K',
    'view.file-push-left': '<Alt>Left',
    'view.file-push-right': '<Alt>Right',
    'view.file-pull-left': '<Alt><shift>Right',
    'view.file-pull-right': '<Alt><shift>Left',
    'view.file-copy-left-up': '<Alt>bracketleft',
    'view.file-copy-right-up': '<Alt>bracketright',
    'view.file-copy-left-down': '<Alt>semicolon',
    'view.file-copy-right-down': '<Alt>quoteright',
    'view.file-delete': ('<Alt>Delete', '<Alt>KP_Delete'),
    'view.show-overview-map': 'F9',
    # Folder comparison actions
    'view.folder-compare': 'Return',
    'view.folder-copy-left': '<Alt>Left',
    'view.folder-copy-right': '<Alt>Right',
    'view.folder-delete': 'Delete',
    # Version control actions
    'view.vc-commit': '<Primary>M',
    'view.vc-console-visible': 'F9',
    # Swap the two panes
    'view.swap-2-panes': '<Alt>backslash',
}


def register_accels(app: Gtk.Application):
    for name, accel in VIEW_ACCELERATORS.items():
        accel = accel if isinstance(accel, tuple) else (accel,)
        app.set_accels_for_action(name, accel)
