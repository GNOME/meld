
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import GtkSource

from meld.conf import _, ui_file
from meld.ui.listselector import FilteredListSelector


class EncodingSelector(FilteredListSelector, Gtk.Grid):
    # The subclassing here is weird; the Selector must directly
    # subclass Gtk.Grid, or the template building explodes.

    __gtype_name__ = 'EncodingSelector'

    __gsignals__ = {
        'encoding-selected': (
            GObject.SignalFlags.RUN_FIRST | GObject.SignalFlags.ACTION,
            None, (GtkSource.Encoding,)),
    }

    # These exist solely to make subclassing easier.
    value_accessor = 'get_charset'
    change_signal_name = 'encoding-selected'

    def populate_model(self):
        for enc in GtkSource.Encoding.get_all():
            self.liststore.append((self.get_value_label(enc), enc))

    def get_value_label(self, enc):
        return _('{name} ({charset})').format(
            name=enc.get_name(), charset=enc.get_charset())


template = open(ui_file('encoding-selector.ui'), 'rb').read()
template_bytes = GLib.Bytes.new(template)
EncodingSelector.set_template(template_bytes)
