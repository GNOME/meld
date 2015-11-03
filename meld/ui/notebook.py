# Copyright (C) 2015 Kai Willadsen <kai.willadsen@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or (at
# your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from gi.repository import Gdk
from gi.repository import GObject
from gi.repository import Gtk


class MeldNotebook(Gtk.Notebook):

    __gtype_name__ = "MeldNotebook"

    __gsignals__ = {
        'tab-switch': (GObject.SignalFlags.ACTION, None, (int,)),
    }

    css = """
        @binding-set TabSwitchBindings {}
        MeldNotebook { gtk-key-bindings: TabSwitchBindings; }
    """

    def __init__(self, *args, **kwargs):
        Gtk.Notebook.__init__(self, *args, **kwargs)

        provider = Gtk.CssProvider()
        provider.load_from_data(self.css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        # Awful hacks because we can't create GtkBindingArg from Python, or
        # create a BindingSet from Python, or get a set by class from Python.
        bindings = Gtk.BindingSet.find('TabSwitchBindings')
        for i in range(10):
            key = (i + 1) % 10
            Gtk.BindingEntry().add_signal_from_string(
                bindings, 'bind "<Alt>%d" { "tab-switch" (%d) };' % (key, i))
        self.connect('tab-switch', self.do_tab_switch)

    def do_tab_switch(self, notebook, page_num):
        notebook.set_current_page(page_num)
