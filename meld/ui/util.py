# Copyright (C) 2013 Kai Willadsen <kai.willadsen@gmail.com>
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

import logging

from gi.repository import Gio, Gtk

import meld.conf
# Import support module to get all builder-constructed widgets in the namespace
from meld.ui import gladesupport  # noqa: F401

log = logging.getLogger(__name__)


def get_widget(filename, widget):
    builder = Gtk.Builder()
    builder.set_translation_domain(meld.conf.__package__)
    path = meld.conf.ui_file(filename)
    builder.add_objects_from_file(path, [widget])
    return builder.get_object(widget)


def get_builder(filename):
    builder = Gtk.Builder()
    builder.set_translation_domain(meld.conf.__package__)
    path = meld.conf.ui_file(filename)
    builder.add_from_file(path)
    return builder


def map_widgets_into_lists(widget, widgetnames):
    """Put sequentially numbered widgets into lists.

    Given an object with widgets self.button0, self.button1, ...,
    after a call to object.map_widgets_into_lists(["button"])
    object.button == [self.button0, self.button1, ...]
    """
    for item in widgetnames:
        i, lst = 0, []
        while 1:
            key = "%s%i" % (item, i)
            try:
                val = getattr(widget, key)
            except AttributeError:
                if i == 0:
                    log.critical(
                        f"Tried to map missing attribute {key}")
                break
            lst.append(val)
            i += 1
        setattr(widget, item, lst)


# The functions `extract_accel_from_menu_item` and `extract_accels_from_menu`
# are converted straight from GTK+'s GtkApplication handling. I don't
# understand why these aren't public API, but here we are.


def extract_accel_from_menu_item(
        model: Gio.MenuModel, item: int, app: Gtk.Application):

    accel, action, target = None, None, None

    more, it = True, model.iterate_item_attributes(item)
    while more:
        more, key, value = it.get_next()
        if key == 'action':
            action = value.get_string()
        elif key == 'accel':
            accel = value.get_string()
        # TODO: Handle targets

    if accel and action:
        detailed_action_name = Gio.Action.print_detailed_name(action, target)
        app.set_accels_for_action(detailed_action_name, [accel])


def extract_accels_from_menu(model: Gio.MenuModel, app: Gtk.Application):
    for i in range(model.get_n_items()):
        extract_accel_from_menu_item(model, i, app)

        more, it = True, model.iterate_item_links(i)
        while more:
            more, name, submodel = it.get_next()
            if submodel:
                extract_accels_from_menu(submodel, app)
