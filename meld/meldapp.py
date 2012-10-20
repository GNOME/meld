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
import re
from gettext import gettext as _

import gobject
import gtk

import misc
import preferences

version = "1.6.1"


class FilterEntry(object):

    __slots__ = ("label", "active", "filter", "filter_string")

    REGEX, SHELL = 0, 1

    def __init__(self, label, active, filter, filter_string):
        self.label = label
        self.active = active
        self.filter = filter
        self.filter_string = filter_string

    @classmethod
    def _compile_regex(cls, regex):
        try:
            compiled = re.compile(regex + "(?m)")
        except re.error:
            compiled = None
        return compiled

    @classmethod
    def _compile_shell_pattern(cls, pattern):
        bits = pattern.split()
        if len(bits) > 1:
            regexes = [misc.shell_to_regex(b)[:-1] for b in bits]
            regex = "(%s)$" % "|".join(regexes)
        elif len(bits):
            regex = misc.shell_to_regex(bits[0])
        else:
            # An empty pattern would match everything, so skip it
            return None

        try:
            compiled = re.compile(regex)
        except re.error:
            compiled = None

        return compiled

    @classmethod
    def parse(cls, string, filter_type):
        elements = string.split("\t")
        if len(elements) < 3:
            return None
        name, active = elements[0], bool(int(elements[1]))
        filter_string = " ".join(elements[2:])
        compiled = FilterEntry.compile_filter(filter_string, filter_type)
        if compiled is None:
            active = False
        return FilterEntry(name, active, compiled, filter_string)

    @classmethod
    def compile_filter(cls, filter_string, filter_type):
        if filter_type == FilterEntry.REGEX:
            compiled = FilterEntry._compile_regex(filter_string)
        elif filter_type == FilterEntry.SHELL:
            compiled = FilterEntry._compile_shell_pattern(filter_string)
        else:
            raise ValueError, "Unknown filter type"
        return compiled

    def __copy__(self):
        new = type(self)(self.label, self.active, None, self.filter_string)
        if self.filter is not None:
            new.filter = re.compile(self.filter.pattern, self.filter.flags)
        return new


class MeldApp(gobject.GObject):

    __gsignals__ = {
        'file-filters-changed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ()),
        'text-filters-changed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ()),
    }

    def __init__(self):
        gobject.GObject.__init__(self)
        gobject.set_application_name("Meld")
        gtk.window_set_default_icon_name("meld")
        self.version = version
        self.prefs = preferences.MeldPreferences()
        self.prefs.notify_add(self.on_preference_changed)
        self.file_filters = self._parse_filters(self.prefs.filters,
                                                FilterEntry.SHELL)
        self.text_filters = self._parse_filters(self.prefs.regexes,
                                                FilterEntry.REGEX)

    def create_window(self):
        self.window = meldwindow.MeldWindow()
        return self.window

    def on_preference_changed(self, key, val):
        if key == "filters":
            self.file_filters = self._parse_filters(val, FilterEntry.SHELL)
            self.emit('file-filters-changed')
        elif key == "regexes":
            self.text_filters = self._parse_filters(val, FilterEntry.REGEX)
            self.emit('text-filters-changed')

    def _parse_filters(self, string, filt_type):
        filt = [FilterEntry.parse(l, filt_type) for l in string.split("\n")]
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
        parser.add_option("-u", "--unified", action="store_true",
                          help=_("Ignored for compatibility"))
        parser.add_option("-o", "--output", action="store", type="string",
            dest="outfile", default=None,
            help=_("Set the target file for saving a merge result"))
        parser.add_option("", "--diff", action="callback", callback=self.diff_files_callback,
                          dest="diff", default=[],
                          help=_("Creates a diff tab for up to 3 supplied files or directories."))
        options, args = parser.parse_args(rawargs)
        if len(args) > 4:
            parser.error(_("too many arguments (wanted 0-4, got %d)") % len(args))
        elif len(args) == 4 and any([os.path.isdir(f) for f in args]):
            parser.error(_("can't compare more than three directories"))

        for files in options.diff:
            if len(files) == 4 and any([os.path.isdir(f) for f in files]):
                parser.error(_("can't compare more than three directories"))
            self.window.open_paths(files)

        tab = self.window.open_paths(args, options.auto_compare)
        if options.label and tab:
            tab.set_labels(options.label)

        if options.outfile and tab and isinstance(tab, filediff.FileDiff):
            tab.set_merge_output_file(options.outfile)


app = MeldApp()

import filediff
import meldwindow

