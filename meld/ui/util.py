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
from typing import List

from gi.repository import Gio, GObject

log = logging.getLogger(__name__)


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

def map_widgets_to_dict(widget, widgetnames):
    """ Put sequentially numbered widgets into dict. """
    for item in widgetnames:
        i, map = 0, {}
        while 1:
            key = "%s%i" % (item, i)
            try:
                val = getattr(widget, key)
            except AttributeError:
                if i == 0:
                    log.critical(
                        f"Tried to map missing attribute {key}")
                break
            map[val] = None
            i += 1
        setattr(widget, item + "_values", map)


def make_multiobject_property_action(
        obj_list: List[GObject.Object], prop_name: str) -> Gio.PropertyAction:
    """Construct a property action linked to multiple objects

    This is useful for creating actions linked to a GObject property,
    where changing the property via the action should affect multiple
    GObjects.

    As an example, changing the text wrapping mode of a file comparison
    pane should change the wrapping mode for *all* panes.
    """
    source, *targets = obj_list
    action = Gio.PropertyAction.new(prop_name, source, prop_name)
    for target in targets:
        source.bind_property(prop_name, target, prop_name)
    return action
