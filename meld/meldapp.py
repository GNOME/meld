### Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
### Copyright (C) 2010-2011 Kai Willadsen <kai.willadsen@gmail.com>

### This program is free software; you can redistribute it and/or modify
### it under the terms of the GNU General Public License as published by
### the Free Software Foundation; either version 2 of the License, or
### (at your option) any later version.

### This program is distributed in the hope that it will be useful,
### but WITHOUT ANY WARRANTY; without even the implied warranty of
### MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
### GNU General Public License for more details.

### You should have received a copy of the GNU General Public License
### along with this program; if not, write to the Free Software
### Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA


import optparse
import os
from gettext import gettext as _

import gobject
import gtk

import preferences

version = "1.5.0"


class MeldApp(object):

    def __init__(self):
        gobject.set_application_name("Meld")
        gtk.window_set_default_icon_name("meld")
        self.version = version
        self.prefs = preferences.MeldPreferences()

    def create_window(self):
        self.window = meldwindow.MeldWindow()
        return self.window

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

        if len(diff_files_args) not in (1, 2, 3, 4):
            raise optparse.OptionValueError(
                _("wrong number of arguments supplied to --diff"))
        parser.values.diff.append(diff_files_args)

    def parse_args(self, rawargs):
        usages = [("", _("Start with an empty window")),
                  ("<%s|%s>" % (_("file"), _("dir")), _("Start a version control comparison")),
                  ("<%s> <%s> [<%s>]" % ((_("file"),) * 3), _("Start a 2- or 3-way file comparison")),
                  ("<%s> <%s> [<%s>]" % ((_("dir"),) * 3), _("Start a 2- or 3-way directory comparison")),
                  ("<%s> <%s>" % (_("file"), _("dir")), _("Start a comparison between file and dir/file"))]
        pad_args_fmt = "%-" + str(max([len(s[0]) for s in usages])) + "s %s"
        usage = "\n" + "\n".join(["  %prog " + pad_args_fmt % u for u in usages])

        parser = optparse.OptionParser(
            usage=usage,
            description=_("Meld is a file and directory comparison tool."),
            version="%prog " + version)
        parser.add_option("-L", "--label", action="append", default=[],
            help=_("Set label to use instead of file name"))
        parser.add_option("-a", "--auto-compare", action="store_true", default=False,
            help=_("Automatically compare all differing files on startup"))
        parser.add_option("-o", "--output", action="store", type="string",
            dest="outfile", default=None,
            help=_("Set the target file for saving a merge result"))
        parser.add_option("", "--diff", action="callback", callback=self.diff_files_callback,
                          dest="diff", default=[],
                          help=_("Creates a diff tab for up to 3 supplied files or directories."))
        options, args = parser.parse_args(rawargs)
        if len(args) > 4:
            parser.error(_("too many arguments (wanted 0-4, got %d)") % len(args))

        for files in options.diff:
            self.open_paths(files)

        tab = self.open_paths(args, options.auto_compare)
        if tab:
            tab.set_labels(options.label)

        if options.outfile and tab and isinstance(tab, filediff.FileDiff):
            tab.set_merge_output_file(options.outfile)

    def open_paths(self, paths, auto_compare=False):
        tab = None
        if len(paths) == 1:
            a = paths[0]
            if os.path.isfile(a):
                self.window._single_file_open(a)
            else:
                tab = self.window.append_vcview(a, auto_compare)
                    
        elif len(paths) in (2, 3, 4):
            tab = self.window.append_diff(paths, auto_compare)
        return tab


app = MeldApp()

import filediff
import meldwindow

