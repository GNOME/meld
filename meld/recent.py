# Copyright (C) 2012 Kai Willadsen <kai.willadsen@gmail.com>

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.

"""
Recent files integration for Meld's multi-element comparisons

The GTK+ recent files mechanism is designed to take only single files with a
limited set of metadata. In Meld, we almost always need to enter pairs or
triples of files or directories, along with some information about the
comparison type. The solution provided by this module is to create fake
single-file registers for multi-file comparisons, and tell the recent files
infrastructure that that's actually what we opened.
"""

import ConfigParser
import os
import sys
import tempfile

from gettext import gettext as _

import gio
import glib
import gtk

from . import misc


TYPE_FILE = "File"
TYPE_FOLDER = "Folder"
TYPE_VC = "Version control"
TYPE_MERGE = "Merge"
COMPARISON_TYPES = (TYPE_FILE, TYPE_FOLDER, TYPE_VC, TYPE_MERGE)


class RecentFiles(object):

    recent_dirname = "Meld" if sys.platform == "win32" else "meld"
    recent_path = os.path.join(glib.get_user_data_dir(), recent_dirname)
    recent_path = recent_path.decode('utf8')
    recent_suffix = ".meldcmp"

    # Recent data
    app_name = "Meld"
    app_exec = "meld"

    def __init__(self, exec_path=None):
        self.recent_manager = gtk.recent_manager_get_default()
        self.recent_filter = gtk.RecentFilter()
        self.recent_filter.add_application(self.app_name)
        self._stored_comparisons = []
        # Should be argv[0] to support roundtripping in uninstalled use
        if exec_path:
            self.app_exec = os.path.abspath(exec_path)

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
        comp_type, paths = tab.get_comparison()

        # While Meld handles comparisons including None, recording these as
        # recently-used comparisons just isn't that sane.
        if None in paths:
            return

        # If a (type, paths) comparison is already registered, then re-add
        # the corresponding comparison file
        comparison_key = (comp_type, tuple(paths))
        if comparison_key in self._stored_comparisons:
            gio_file = gio.File(uri=self._stored_comparisons[comparison_key])
        else:
            recent_path = self._write_recent_file(comp_type, paths)
            gio_file = gio.File(path=recent_path)

        if len(paths) > 1:
            display_name = " : ".join(misc.shorten_names(*paths))
        else:
            display_path = paths[0]
            userhome = os.path.expanduser("~")
            if display_path.startswith(userhome):
                # FIXME: What should we show on Windows?
                display_path = "~" + display_path[len(userhome):]
            display_name = _("Version control:") + " " + display_path
        # FIXME: Should this be translatable? It's not actually used anywhere.
        description = "%s comparison\n%s" % (comp_type, ", ".join(paths))

        recent_metadata = {
            "mime_type": "application/x-meld-comparison",
            "app_name": self.app_name,
            "app_exec": "%s --comparison-file %%u" % self.app_exec,
            "display_name": display_name.encode('utf8'),
            "description": description.encode('utf8'),
            "is_private": True,
        }
        self.recent_manager.add_full(gio_file.get_uri(), recent_metadata)

    def read(self, uri):
        """Read stored comparison from URI

        Returns the comparison type, the paths involved and the comparison
        flags.
        """
        gio_file = gio.File(uri=uri)
        path = gio_file.get_path()
        if not gio_file.query_exists() or not path:
            raise IOError("File does not exist")

        try:
            config = ConfigParser.RawConfigParser()
            config.read(path)
            assert (config.has_section("Comparison") and
                    config.has_option("Comparison", "type") and
                    config.has_option("Comparison", "paths"))
        except (ConfigParser.Error, AssertionError):
            raise ValueError("Invalid recent comparison file")

        comp_type = config.get("Comparison", "type")
        paths = tuple(config.get("Comparison", "paths").split(";"))
        flags = tuple()

        if comp_type not in COMPARISON_TYPES:
            raise ValueError("Invalid recent comparison file")

        return comp_type, paths, flags

    def _write_recent_file(self, comp_type, paths):
        # TODO: Use GKeyFile instead, and return a gio.File. This is why we're
        # using ';' to join comparison paths.
        with tempfile.NamedTemporaryFile(prefix='recent-',
                                         suffix=self.recent_suffix,
                                         dir=self.recent_path,
                                         delete=False) as f:
            config = ConfigParser.RawConfigParser()
            config.add_section("Comparison")
            config.set("Comparison", "type", comp_type)
            config.set("Comparison", "paths", ";".join(paths))
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
        item_paths = [gio.File(uri=uri).get_path() for uri in item_uris]
        stored = [p for p in os.listdir(self.recent_path)
                  if p.endswith(self.recent_suffix)]
        for path in stored:
            file_path = os.path.abspath(os.path.join(self.recent_path, path))
            if file_path not in item_paths:
                os.remove(file_path)

    def _update_recent_files(self, *args):
        meld_items = self._filter_items(self.recent_filter,
                                        self.recent_manager.get_items())
        item_uris = [item.get_uri() for item in meld_items if item.exists()]
        self._stored_comparisons = {}
        for uri in item_uris:
            try:
                comp = self.read(uri)
            except (IOError, ValueError):
                continue
            # Store and look up comparisons by type and paths, ignoring flags
            self._stored_comparisons[comp[:2]] = uri

    def _filter_items(self, recent_filter, items):
        getters = {gtk.RECENT_FILTER_URI: "uri",
                   gtk.RECENT_FILTER_DISPLAY_NAME: "display_name",
                   gtk.RECENT_FILTER_MIME_TYPE: "mime_type",
                   gtk.RECENT_FILTER_APPLICATION: "applications",
                   gtk.RECENT_FILTER_GROUP: "groups",
                   gtk.RECENT_FILTER_AGE: "age"}
        needed = recent_filter.get_needed()
        attrs = [v for k, v in getters.iteritems() if needed & k]

        filtered_items = []
        for i in items:
            filter_info = {}
            for attr in attrs:
                filter_info[attr] = getattr(i, "get_" + attr)()
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


if __name__ == "__main__":
    recent = RecentFiles()
    print recent
