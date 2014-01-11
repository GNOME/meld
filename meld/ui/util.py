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

import os

from gi.repository import Gtk

import meld.conf

# Import support module to get all builder-constructed widgets in the namespace
from meld.ui import gladesupport


def ui_file(filename):
    return os.path.join(meld.conf.DATADIR, "ui", filename)


def get_widget(filename, widget):
    builder = Gtk.Builder()
    builder.set_translation_domain(meld.conf.__package__)
    builder.add_objects_from_file(ui_file(filename), [widget])
    return builder.get_object(widget)


def get_builder(filename):
    builder = Gtk.Builder()
    builder.set_translation_domain(meld.conf.__package__)
    builder.add_from_file(ui_file(filename))
    return builder
