# Copyright (C) 2012-2013, 2017-2018 Kai Willadsen <kai.willadsen@gmail.com>
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

"""
Recent files integration for Meld's multi-element comparisons

The GTK+ recent files mechanism is designed to take only single files with a
limited set of metadata. In Meld, we almost always need to enter pairs or
triples of files or directories, along with some information about the
comparison type. The solution provided by this module is to create fake
single-file registers for multi-file comparisons, and tell the recent files
infrastructure that that's actually what we opened.
"""

import configparser
import enum
import logging
import os
import sys
import tempfile
from typing import List, Tuple

from gi.repository import Gio, GLib, Gtk

import meld.misc
from meld.conf import _
from meld.iohelpers import is_file_on_tmpfs

log = logging.getLogger(__name__)


class RecentType(enum.Enum):
    File = "File"
    Folder = "Folder"
    VersionControl = "Version control"
    Merge = "Merge"


class RecentFiles:

    mime_type = "application/x-meld-comparison"
    recent_path = os.path.join(GLib.get_user_data_dir(), "meld")
    recent_suffix = ".meldcmp"

    # Recent data
    app_name = "Meld"

    def __init__(self):
        self.recent_manager = Gtk.RecentManager.get_default()
        self.recent_filter = Gtk.RecentFilter()
        self.recent_filter.add_mime_type(self.mime_type)
        self._stored_comparisons = {}
        self.app_exec = os.path.abspath(sys.argv[0])

        if not os.path.exists(self.recent_path):
            os.makedirs(self.recent_path)

        self._clean_recent_files()
        self._update_recent_files()
        self.recent_manager.connect("changed", self._update_recent_files)

    def add(self, tab, flags=None):
        """Add a tab to our recently-used comparison list

        The passed flags are currently ignored. In the future these are to be
        used for extra initialisation not captured by the tab itself.
        """
        try:
            recent_type, gfiles = tab.get_comparison()
        except Exception:
            log.warning(f'Failed to get recent comparison data for {tab}')
            return

        # While Meld handles comparisons including None, recording these as
        # recently-used comparisons just isn't that sane.
        if not gfiles or None in gfiles:
            return

        if any(is_file_on_tmpfs(f) for f in gfiles):
            log.debug("Not adding comparison because it includes tmpfs path")
            return

        uris = [f.get_uri() for f in gfiles]
        if not all(uris):
            return

        names = [f.get_parse_name() for f in gfiles]

        # If a (type, uris) comparison is already registered, then re-add
        # the corresponding comparison file
        comparison_key = (recent_type, tuple(uris))
        if comparison_key in self._stored_comparisons:
            gfile = Gio.File.new_for_uri(
                self._stored_comparisons[comparison_key])
        else:
            recent_path = self._write_recent_file(recent_type, uris)
            gfile = Gio.File.new_for_path(recent_path)

        if len(uris) > 1:
            display_name = " : ".join(meld.misc.shorten_names(*names))
        else:
            display_path = names[0]
            userhome = os.path.expanduser("~")
            if display_path.startswith(userhome):
                # FIXME: What should we show on Windows?
                display_path = "~" + display_path[len(userhome):]
            display_name = _("Version control:") + " " + display_path
        # FIXME: Should this be translatable? It's not actually used anywhere.
        description = "{} comparison\n{}".format(
            recent_type.value, ", ".join(uris))

        recent_metadata = Gtk.RecentData()
        recent_metadata.mime_type = self.mime_type
        recent_metadata.app_name = self.app_name
        recent_metadata.app_exec = "%s --comparison-file %%u" % self.app_exec
        recent_metadata.display_name = display_name
        recent_metadata.description = description
        recent_metadata.is_private = True
        self.recent_manager.add_full(gfile.get_uri(), recent_metadata)

    def read(self, uri: str) -> Tuple[RecentType, List[Gio.File]]:
        """Read stored comparison from URI"""
        comp_gfile = Gio.File.new_for_uri(uri)
        comp_path = comp_gfile.get_path()
        if not comp_gfile.query_exists(None) or not comp_path:
            raise IOError("Recent comparison file does not exist")

        try:
            config = configparser.RawConfigParser()
            config.read(comp_path)
            assert (config.has_section("Comparison") and
                    config.has_option("Comparison", "type") and
                    config.has_option("Comparison", "uris"))
        except (configparser.Error, AssertionError):
            raise ValueError("Invalid recent comparison file")

        try:
            recent_type = RecentType(config.get("Comparison", "type"))
        except ValueError:
            raise ValueError("Invalid recent comparison file")

        uris = config.get("Comparison", "uris").split(";")
        gfiles = [Gio.File.new_for_uri(u) for u in uris]

        return recent_type, gfiles

    def _write_recent_file(self, recent_type: RecentType, uris):
        # TODO: Use GKeyFile instead, and return a Gio.File. This is why we're
        # using ';' to join comparison paths.
        with tempfile.NamedTemporaryFile(
                mode='w+t', prefix='recent-', suffix=self.recent_suffix,
                dir=self.recent_path, delete=False) as f:
            config = configparser.RawConfigParser()
            config.add_section("Comparison")
            config.set("Comparison", "type", recent_type.value)
            config.set("Comparison", "uris", ";".join(uris))
            config.write(f)
            name = f.name
        return name

    def _clean_recent_files(self):
        # Remove from RecentManager any comparisons with no existing file
        meld_items = self._filter_items(self.recent_filter,
                                        self.recent_manager.get_items())
        for item in meld_items:
            if not item.exists():
                self.recent_manager.remove_item(item.get_uri())

        meld_items = [item for item in meld_items if item.exists()]

        # Remove any comparison files that are not listed by RecentManager
        item_uris = [item.get_uri() for item in meld_items]
        item_paths = [
            Gio.File.new_for_uri(uri).get_path() for uri in item_uris]
        stored = [p for p in os.listdir(self.recent_path)
                  if p.endswith(self.recent_suffix)]
        for path in stored:
            file_path = os.path.abspath(os.path.join(self.recent_path, path))
            if file_path not in item_paths:
                try:
                    os.remove(file_path)
                except OSError:
                    pass

    def _update_recent_files(self, *args):
        meld_items = self._filter_items(self.recent_filter,
                                        self.recent_manager.get_items())
        item_uris = [item.get_uri() for item in meld_items if item.exists()]
        self._stored_comparisons = {}
        for item_uri in item_uris:
            try:
                recent_type, gfiles = self.read(item_uri)
            except (IOError, ValueError):
                continue
            # Store and look up comparisons by type and paths
            gfile_uris = tuple(gfile.get_uri() for gfile in gfiles)
            self._stored_comparisons[recent_type, gfile_uris] = item_uri

    def _filter_items(self, recent_filter, items):
        getters = {Gtk.RecentFilterFlags.URI: "uri",
                   Gtk.RecentFilterFlags.DISPLAY_NAME: "display_name",
                   Gtk.RecentFilterFlags.MIME_TYPE: "mime_type",
                   Gtk.RecentFilterFlags.APPLICATION: "applications",
                   Gtk.RecentFilterFlags.GROUP: "groups",
                   Gtk.RecentFilterFlags.AGE: "age"}
        needed = recent_filter.get_needed()
        attrs = [v for k, v in getters.items() if needed & k]

        filtered_items = []
        for i in items:
            filter_data = {}
            for attr in attrs:
                filter_data[attr] = getattr(i, "get_" + attr)()
            filter_info = Gtk.RecentFilterInfo()
            filter_info.contains = needed
            for f, v in filter_data.items():
                # https://bugzilla.gnome.org/show_bug.cgi?id=695970
                if isinstance(v, list):
                    continue
                setattr(filter_info, f, v)
            if recent_filter.filter(filter_info):
                filtered_items.append(i)
        return filtered_items

    def __str__(self):
        items = self.recent_manager.get_items()
        descriptions = []
        for i in self._filter_items(self.recent_filter, items):
            descriptions.append("%s\n%s\n" % (i.get_display_name(),
                                              i.get_uri_display()))
        return "\n".join(descriptions)


recent_comparisons = RecentFiles()
