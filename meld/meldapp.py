# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2010-2013 Kai Willadsen <kai.willadsen@gmail.com>
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

from __future__ import print_function

import optparse
import os
from gettext import gettext as _

from gi.repository import Gio
from gi.repository import GLib
from gi.repository import Gdk
from gi.repository import Gtk

import meld.conf
import meld.preferences
import meld.ui.util


class MeldApp(Gtk.Application):

    def __init__(self):
        Gtk.Application.__init__(self)
        self.set_flags(Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.set_application_id("org.gnome.meld")
        GLib.set_application_name("Meld")
        Gtk.Window.set_default_icon_name("meld")

    def do_startup(self):
        Gtk.Application.do_startup(self)

        actions = (
            ("preferences", self.preferences_callback),
            ("help", self.help_callback),
            ("about", self.about_callback),
            ("quit", self.quit_callback),
        )
        for (name, callback) in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', callback)
            self.add_action(action)

        # TODO: Should not be necessary but Builder doesn't understand Menus
        builder = meld.ui.util.get_builder("application.ui")
        menu = builder.get_object("app-menu")
        self.set_app_menu(menu)
        # self.set_menubar()
        self.new_window()

    def do_activate(self):
        self.get_active_window().present()

    def do_command_line(self, command_line):
        self.register(None)
        self.activate()
        tab = self.parse_args(command_line.get_arguments()[1:],
                              is_first=not command_line.get_is_remote())
        if tab:
            def done(tab, status):
                self.release()
                tab.command_line.set_exit_status(status)
                tab.command_line = None

            self.hold()
            tab.command_line = command_line
            tab.connect('close', done)
        window = self.get_active_window().meldwindow
        if not window.has_pages():
            window.append_new_comparison()
        return 0

    def do_window_removed(self, widget):
        widget.meldwindow = None
        Gtk.Application.do_window_removed(self, widget)

    # We can't override do_local_command_line because it has no introspection
    # annotations: https://bugzilla.gnome.org/show_bug.cgi?id=687912
    # Uniqueness handling is instead hackily done in the launcher script.

    # def do_local_command_line(self, command_line):
    #     return False

    def preferences_callback(self, action, parameter):
        meld.preferences.PreferencesDialog(self.get_active_window())

    def help_callback(self, action, parameter):
        Gtk.show_uri(Gdk.Screen.get_default(), "help:meld",
                     Gtk.get_current_event_time())

    def about_callback(self, action, parameter):
        about = meld.ui.util.get_widget("application.ui", "aboutdialog")
        about.set_version(meld.conf.__version__)
        about.set_transient_for(self.get_active_window())
        about.run()
        about.destroy()

    def quit_callback(self, action, parameter):
        for window in self.get_windows():
            cancelled = window.emit("delete-event",
                                    Gdk.Event(Gdk.EventType.DELETE))
            if cancelled:
                return
            window.destroy()
        self.quit()

    def new_window(self):
        window = meldwindow.MeldWindow()
        self.add_window(window.widget)
        window.widget.meldwindow = window
        window.widget.show()
        return window

    def open_paths(self, paths, **kwargs):
        new_tab = kwargs.pop('new_tab')
        if new_tab:
            window = self.get_active_window().meldwindow
        else:
            window = self.new_window()
        return window.open_paths(paths, **kwargs)

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

    def parse_args(self, rawargs, is_first=True):
        usages = [
            ("", _("Start with an empty window")),
            ("<%s|%s>" % (_("file"), _("folder")),
             _("Start a version control comparison")),
            ("<%s> <%s> [<%s>]" % ((_("file"),) * 3),
             _("Start a 2- or 3-way file comparison")),
            ("<%s> <%s> [<%s>]" % ((_("folder"),) * 3),
             _("Start a 2- or 3-way folder comparison")),
        ]
        pad_args_fmt = "%-" + str(max([len(s[0]) for s in usages])) + "s %s"
        usage_lines = ["  %prog " + pad_args_fmt % u for u in usages]
        usage = "\n" + "\n".join(usage_lines)

        parser = optparse.OptionParser(
            usage=usage,
            description=_("Meld is a file and directory comparison tool."),
            version="%prog " + meld.conf.__version__)
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

        if options.comparison_file or (len(args) == 1 and
                                       args[0].endswith(".meldcmp")):
            path = options.comparison_file or args[0]
            comparison_file_path = os.path.expanduser(path)
            gio_file = Gio.File.new_for_path(comparison_file_path)
            try:
                tab = self.window.append_recent(gio_file.get_uri())
            except (IOError, ValueError):
                parser.error(_("Error reading saved comparison file"))
            return tab

        error = None
        comparisons = options.diff + [args]
        options.newtab = options.newtab or is_first
        for i, paths in enumerate(comparisons):
            try:
                tab = self.open_paths(
                    paths, auto_compare=options.auto_compare,
                    auto_merge=options.auto_merge, new_tab=options.newtab,
                    focus=i == 0)
            except ValueError as err:
                error = err

            if options.label:
                tab.set_labels(options.label)

            if options.outfile and isinstance(tab, filediff.FileDiff):
                tab.set_merge_output_file(options.outfile)

        if error:
            if not self.window.has_pages():
                parser.error(error)
            else:
                print(error)

        return tab if len(comparisons) == 1 else None


app = MeldApp()

from . import filediff
from . import meldwindow
