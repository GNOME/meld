# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2010-2012 Kai Willadsen <kai.willadsen@gmail.com>

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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.

from __future__ import print_function

import logging
import optparse
import os
import sys
from gettext import gettext as _

import gio
import gobject
import gtk

from . import conf
from . import filters
from . import preferences
from . import recent


class MeldApp(gobject.GObject):

    __gsignals__ = {
        'file-filters-changed': (gobject.SIGNAL_RUN_FIRST,
                                 gobject.TYPE_NONE, ()),
        'text-filters-changed': (gobject.SIGNAL_RUN_FIRST,
                                 gobject.TYPE_NONE, ()),
    }

    def __init__(self):
        gobject.GObject.__init__(self)
        gobject.set_application_name("Meld")
        gtk.window_set_default_icon_name("meld")
        self.version = conf.VERSION
        self.prefs = preferences.MeldPreferences()
        self.prefs.notify_add(self.on_preference_changed)
        self.file_filters = self._parse_filters(self.prefs.filters,
                                                filters.FilterEntry.SHELL)
        self.text_filters = self._parse_filters(self.prefs.regexes,
                                                filters.FilterEntry.REGEX)
        self.recent_comparisons = recent.RecentFiles(sys.argv[0])

    def create_window(self):
        self.window = meldwindow.MeldWindow()
        return self.window

    def on_preference_changed(self, key, val):
        if key == "filters":
            self.file_filters = self._parse_filters(val,
                                                    filters.FilterEntry.SHELL)
            self.emit('file-filters-changed')
        elif key == "regexes":
            self.text_filters = self._parse_filters(val,
                                                    filters.FilterEntry.REGEX)
            self.emit('text-filters-changed')

    def _parse_filters(self, string, filt_type):
        filt = [filters.FilterEntry.parse(l, filt_type) for l
                in string.split("\n")]
        return [f for f in filt if f is not None]

    def diff_files_callback(self, option, opt_str, value, parser):
        """Gather --diff arguments and append to a list"""
        assert value is None
        diff_files_args = []
        while parser.rargs:
            # Stop if we find a short- or long-form arg, or a '--'
            # Note that this doesn't handle negative numbers.
            arg = parser.rargs[0]
            if arg[:2] == "--" or (arg[:1] == "-" and len(arg) > 1):
                break
            else:
                diff_files_args.append(arg)
                del parser.rargs[0]

        if len(diff_files_args) not in (1, 2, 3):
            raise optparse.OptionValueError(
                _("wrong number of arguments supplied to --diff"))
        parser.values.diff.append(diff_files_args)

    def parse_args(self, rawargs):
        usages = [("", _("Start with an empty window")),
                  ("<%s|%s>" % (_("file"), _("dir")),
                   _("Start a version control comparison")),
                  ("<%s> <%s> [<%s>]" % ((_("file"),) * 3),
                   _("Start a 2- or 3-way file comparison")),
                  ("<%s> <%s> [<%s>]" % ((_("dir"),) * 3),
                   _("Start a 2- or 3-way directory comparison")),
                  ("<%s> <%s>" % (_("file"), _("dir")),
                   _("Start a comparison between file and dir/file"))]
        pad_args_fmt = "%-" + str(max([len(s[0]) for s in usages])) + "s %s"
        usage_lines = ["  %prog " + pad_args_fmt % u for u in usages]
        usage = "\n" + "\n".join(usage_lines)

        parser = optparse.OptionParser(
            usage=usage,
            description=_("Meld is a file and directory comparison tool."),
            version="%prog " + conf.VERSION)
        parser.add_option("-L", "--label", action="append", default=[],
            help=_("Set label to use instead of file name"))
        parser.add_option("-n", "--newtab", action="store_true", default=False,
            help=_("Open a new tab in an already running instance"))
        parser.add_option("-a", "--auto-compare", action="store_true",
            default=False,
            help=_("Automatically compare all differing files on startup"))
        parser.add_option("-u", "--unified", action="store_true",
                          help=_("Ignored for compatibility"))
        parser.add_option("-o", "--output", action="store", type="string",
            dest="outfile", default=None,
            help=_("Set the target file for saving a merge result"))
        parser.add_option("--auto-merge", None, action="store_true",
            default=False, help=_("Automatically merge files"))
        parser.add_option("", "--comparison-file", action="store",
            type="string", dest="comparison_file", default=None,
            help=_("Load a saved comparison from a Meld comparison file"))
        parser.add_option("", "--diff", action="callback",
            callback=self.diff_files_callback, dest="diff", default=[],
            help=_("Create a diff tab for the supplied files or folders"))
        options, args = parser.parse_args(rawargs)
        if len(args) > 3:
            parser.error(_("too many arguments (wanted 0-3, got %d)") % \
                         len(args))
        elif options.auto_merge and len(args) < 3:
            parser.error(_("can't auto-merge less than 3 files"))
        elif options.auto_merge and any([os.path.isdir(f) for f in args]):
            parser.error(_("can't auto-merge directories"))

        new_window = True
        open_paths = self.window.open_paths
        if options.newtab:
            if not dbus_app:
                print(_("D-Bus error; comparisons will open in a new window."))
            else:
                # Note that we deliberately discard auto-compare and -merge
                # options here; these are not supported via dbus yet.
                open_paths = lambda f, *x: dbus_app.OpenPaths(f, 0)
                new_window = False

        for files in options.diff:
            open_paths(files)

        if options.comparison_file or (len(args) == 1 and
                                       args[0].endswith(".meldcmp")):
            path = options.comparison_file or args[0]
            comparison_file_path = os.path.expanduser(path)
            gio_file = gio.File(path=comparison_file_path)
            try:
                tab = self.window.append_recent(gio_file.get_uri())
            except (IOError, ValueError):
                parser.error(_("Error reading saved comparison file"))
        elif args:
            tab = open_paths(args, options.auto_compare, options.auto_merge)
        else:
            tab = None

        if options.label and tab:
            tab.set_labels(options.label)

        if not self.window.has_pages():
            self.window.append_new_comparison()

        if options.outfile and tab and isinstance(tab, filediff.FileDiff):
            tab.set_merge_output_file(options.outfile)

        return new_window


log = logging.getLogger("meld")

# If we're running uninstalled and from Git, turn up the logging level
top_level = os.path.dirname(os.path.dirname(__file__))
if os.path.exists(os.path.join(top_level, "meld.doap")) and \
   os.path.exists(os.path.join(top_level, ".git")):
    log.setLevel(logging.WARNING)
else:
    log.setLevel(logging.CRITICAL)

handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s %(levelname)s "
                              "%(name)s: %(message)s")
handler.setFormatter(formatter)
log.addHandler(handler)

app = MeldApp()
dbus_app = None

from . import filediff
from . import meldwindow
