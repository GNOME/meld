### Copyright (C) 2002-2004 Stephen Kennedy <stevek@gnome.org>

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

# system
import sys
import os

# gnome
import gtk

# project
import paths
import glade
import misc
import task
import stock
import filediff
import dirdiff
import cvsview

import prefs
import prefsui

try:
    import dbus
except ImportError:
    import fakedbus as dbus

version = "1.1.0"

# magic developer switch, changes some behaviour
developer = 0

class MeldApp(glade.GtkApp, dbus.Object):

    UI_DEFINITION = """
    <ui>
      <menubar name="MenuBar">
        <menu action="file_menu">
          <menuitem action="new"/>
          <separator/>
          <placeholder name="file_extras"/>
          <menuitem action="quit"/>
        </menu>
        <placeholder name="menu_extras"/>
        <menu action="settings_menu">
          <menuitem action="preferences"/>
        </menu>
        <menu action="help_menu">
          <menuitem action="help_contents"/>
          <menuitem action="reportbug"/>
          <menuitem action="about"/>
        </menu>
      </menubar>
      <toolbar name="ToolBar">
          <toolitem action="new"/>
      </toolbar>
    </ui>
    """

    UI_ACTIONS = (
        ('file_menu', None, _('_File')),
            ('new', gtk.STOCK_NEW,
                _('_New...'), '<Control>n', _('Open a new tab')),
            ('quit', gtk.STOCK_QUIT,
                _('_Quit'), '<Control>q', _('Quit the application')),

        ('settings_menu', None, _('_Settings')),
            ('preferences', gtk.STOCK_PREFERENCES,
                _('_Preferences'), None, _('Configure preferences')),

        ('help_menu', None, _('_Help')),
            ('help_contents', gtk.STOCK_HELP,
                _('_Contents'), "F1", _('Users manual')),
            ('reportbug', stock.STOCK_REPORTBUG,
                _('_Report Bug'), None, _('Report a bug')),
            ('about', stock.STOCK_ABOUT,
                _('_About'), None, _('About the application')),
    )

    #
    # init
    #
    def __init__(self, dbus_service):
        glade.GtkApp.__init__(self, paths.share_dir("glade2/meldapp.glade"), "meldapp")

        self.uimanager = gtk.UIManager()
        self.toplevel.add_accel_group( self.uimanager.get_accel_group() )
        self.actiongroup = gtk.ActionGroup("AppActions")
        self.add_actions( self.actiongroup, self.UI_ACTIONS )
        self.uimanager.insert_action_group(self.actiongroup, 0)
        self.uimanager.add_ui_from_string(self.UI_DEFINITION)

        self.menubar = self.uimanager.get_widget('/MenuBar')
        self.toolbar = self.uimanager.get_widget('/ToolBar')
        self.vbox.pack_start(self.menubar, False)
        self.vbox.reorder_child(self.menubar, 0)
        self.vbox.pack_start(self.toolbar, False)
        self.vbox.reorder_child(self.toolbar, 1)

        self.connect_signal_handlers()
        self.prefs = prefsui.MeldPreferences()

        self.toolbar.set_style( self.prefs.get_toolbar_style() )
        self.prefs.notify_add( self.on_preference_changed )
        self.idle_hooked = 0
        self.scheduler = task.LifoScheduler()
        self.scheduler.connect("runnable", self.on_scheduler_runnable )
        self.toplevel.set_default_size(self.prefs.window_size_x, self.prefs.window_size_y)
        self.toplevel.show()
        if dbus_service:
            dbus.Object.__init__(self, "/App", dbus_service,
                [self.action_about__activate] )

    def _set_doc_status(self, status):
        self.doc_status.pop(1)
        self.doc_status.push(1,status)

    #
    # Scheduler
    #
    def on_idle(self):
        def _set_task_status(status):
            self.task_status.pop(1)
            self.task_status.push(1,status)

        ret = self.scheduler.iteration()
        if ret:
            if type(ret) in (type(""), type(u"")):
                _set_task_status(ret)
            elif type(ret) == type(0.0):
                self.task_progress.set_fraction(ret)
            else:
                self.task_progress.pulse()
        else:
            self.task_progress.set_fraction(0)
        if self.scheduler.tasks_pending():
            return 1
        else:
            _set_task_status("")
            self.idle_hooked = 0
            return 0

    def on_scheduler_runnable(self, sched):
        if not self.idle_hooked:
            self.idle_hooked = 1
            gtk.idle_add( self.on_idle )

    def on_preference_changed(self, key, value):
        if key == "toolbar_style":
            self.toolbar.set_style( self.prefs.get_toolbar_style() )

    #
    # General events and callbacks
    #
    def on_toplevel__delete_event(self, *extra):
        return self.action_quit__activate()

    def on_toplevel__size_allocate(self, window, rect):
        self.prefs.window_size_x = rect.width
        self.prefs.window_size_y = rect.height

    def on_notebook__switch_page(self, notebook, page, which):
        newdoc = notebook.get_nth_page(which).get_data("pyobject")
        nbl = self.notebook.get_tab_label( newdoc.toplevel )
        self.toplevel.set_title( nbl.label.get_text() + " - Meld")
        self._set_doc_status("")
        newdoc.on_container_switch_event()
        self.scheduler.add_task( newdoc.scheduler )

    def on_notebook_label_changed(self, component, text):
        nbl = self.notebook.get_tab_label( component.toplevel )
        nbl.set_text(text)
        self.toplevel.set_title(text + " - Meld")
        self.notebook.child_set_property(component.toplevel, "menu-label", text)

    #
    # File actions
    #
    def action_new__activate(self, *extra):
        NewDocDialog(self, NewDocDialog.TYPE.DIFF2)

    def action_quit__activate(self, *extra):
        if not developer:
            for c in self.notebook.get_children():
                response = c.get_data("pyobject").on_container_delete_event(app_quit=1)
                if response == gtk.RESPONSE_CANCEL:
                    return gtk.RESPONSE_CANCEL
                elif response == gtk.RESPONSE_CLOSE:
                    break
        for c in self.notebook.get_children():
            c.get_data("pyobject").on_container_quit_event()
        self.quit()

    #
    # Settings actions
    #
    def action_preferences__activate(self, *extra):
        prefsui.PreferencesDialog(self)

    #
    # Help actions
    #
    def action_help_contents__activate(self, *extra):
        print "file:///"+os.path.abspath(paths.doc_dir("meld.xml"))
        glade.url_show("file:///"+os.path.abspath(paths.doc_dir("meld.xml") ), self)

    def action_reportbug__activate(self, *extra):
        glade.url_show("http://bugzilla.gnome.org/buglist.cgi?product=meld", self)

    def action_about__activate(self, *extra):
        class About(glade.Dialog):
            def __init__(self, parent):
                glade.Component.__init__(self, paths.share_dir("glade2/meldapp.glade"), "about")
                self.connect_signal_handlers()
                self.toplevel.set_transient_for(parent)
                self.label_version.set_markup('<span size="xx-large" weight="bold">Meld %s</span>' % version)
            #def on_button_home_page__clicked(self, *args):
            #    print "XXX fixme"
            def on_button_credits__clicked(self, *args):
                class Credits(glade.Dialog):
                    def __init__(self, parent):
                        glade.Component.__init__(self, paths.share_dir("glade2/meldapp.glade"), "about_credits")
                        self.toplevel.set_transient_for(parent)
                Credits(self.toplevel.get_toplevel()).run()
                return True
            def on_button_close__clicked(self, *args):
                self.toplevel.destroy()
        About( self.toplevel.get_toplevel() )

    #
    #
    #
    def try_remove_page(self, page):
        """Remove a page if the doc allows it.
        """
        if page.on_container_delete_event() == gtk.RESPONSE_OK:
            self.remove_page(page)

    def remove_page(self, page):
        """Unconditionally remove a page.
        """
        self.scheduler.remove_scheduler( page.scheduler )
        self.uimanager.remove_action_group( page.actiongroup )
        self.uimanager.remove_ui( page.ui_merge_id )
        self.toplevel.set_title("Meld")
        self._set_doc_status("")
        self.notebook.remove_page( self.notebook.page_num(page.toplevel) )

    def on_file_changed(self, srcpage, filename):
        """A page has changed a file.
        """
        for c in self.notebook.get_children():
            page = c.get_data("pyobject")
            if page != srcpage:
                page.on_container_file_changed(filename)

    def _append_page(self, page, icon):
        """Common page append code.
        """
        nbl = glade.CloseLabel(icon)
        nbl.connect("closed", lambda b: self.try_remove_page(page))
        self.notebook.append_page( page.toplevel, nbl)
        self.notebook.set_current_page( self.notebook.page_num(page.toplevel) )
        self.scheduler.add_scheduler(page.scheduler)
        page.connect("label-changed", self.on_notebook_label_changed)
        page.connect("file-changed", self.on_file_changed)
        page.connect("create-diff", lambda obj,arg: self.append_filediff(arg) )
        page.connect("status-changed", lambda junk,arg: self._set_doc_status(arg) )
        page.connect("closed", lambda page: self.remove_page(page) )
        self.uimanager.insert_action_group(page.actiongroup, 1)
        page.ui_merge_id = self.uimanager.add_ui_from_string(page.UI_DEFINITION)

    def append_dirdiff(self, dirs):
        assert len(dirs) in (1,2,3)
        doc = dirdiff.DirDiff(self.prefs, len(dirs))
        self._append_page(doc, "tree-folder-normal.png")
        doc.set_locations(dirs)

    def append_filediff(self, files):
        assert len(files) in (1,2,3)
        doc = filediff.FileDiff(self.prefs, len(files))
        self._append_page(doc, "tree-file-normal.png")
        doc.set_files(files)

    def append_diff(self, paths):
        aredirs = [ os.path.isdir(p) for p in paths ]
        arefiles = [ os.path.isfile(p) for p in paths ]
        if (1 in aredirs) and (1 in arefiles):
            main = _("Cannot compare a mixture of files and directories.\n")
            extra = []
            for i in range(len(paths)):
                what = aredirs[i] and _("folder") \
                    or arefiles[i] and _("file") \
                    or _("nonexistant")
                extra.append( "(%s)\t`%s'" % (what, paths[i]) )
            glade.run_dialog( main,
                    self.toplevel,
                    buttonstype = gtk.BUTTONS_OK,
                    subtext = "\n".join(extra) )
        elif 1 in aredirs:
            self.append_dirdiff(paths)
        else:
            self.append_filediff(paths)

    def append_version(self, locations):
        assert len(locations) in (1,)
        location = locations[0]
        doc = cvsview.CvsView(self.prefs)
        self._append_page(doc, "cvs-icon.png")
        doc.set_location(location)

    #
    # Usage
    #
    def usage(self, msg):
        response = glade.run_dialog(msg,
            self.toplevel,
            gtk.MESSAGE_ERROR,
            gtk.BUTTONS_NONE,
            [(gtk.STOCK_QUIT, gtk.RESPONSE_CANCEL), (gtk.STOCK_OK, gtk.RESPONSE_OK)] ,
            subtext=_("Run meld --help for help"))
        if response == gtk.RESPONSE_CANCEL:
            sys.exit(0)
        
        
class NewDocDialog(glade.Component):

    TYPE = misc.struct(DIFF2=0, DIFF3=1, DIR2=2, DIR3=3, CVS=4, SVN=6)
         
    def __init__(self, parentapp, type):
        self.parentapp = parentapp
        glade.Component.__init__(self, paths.share_dir("glade2/meldapp.glade"), "newdialog")
        self.map_widgets_into_lists( ("fileentry", "direntry", "versionentry", "three_way_compare", "tablabel") )
        self.entrylists = self.fileentry, self.direntry, self.versionentry
        self.connect_signal_handlers()
        glade.tie_to_gconf("/apps/meld/state/new", self.three_way_compare, self.version_autodetect)
        self.toplevel.set_transient_for(parentapp.toplevel)
        cur_page = type // 2
        self.notebook.set_current_page( cur_page )
        for e in self.fileentry + self.direntry + self.versionentry:
            e.entry.connect("activate", self._on_entry__activate)
        self.toplevel.show_all()

    def _on_entry__activate(self, gtkentry):
        entry = gtkentry.parent.parent
        for el in self.entrylists:
            if entry in el:
                i = el.index(entry)
                if i == len(el) - 1:
                    self.button_ok.grab_focus()
                else:
                    el[i+1].entry.grab_focus()

    def on_three_way_compare__toggled(self, button):
        page = self.three_way_compare.index(button)
        self.entrylists[page][0].set_sensitive( button.get_active() )
        if button.flags() & gtk.REALIZED == gtk.REALIZED:
            self.entrylists[page][ not button.get_active() ].entry.grab_focus()

    def on_toplevel__response(self, dialog, arg):
        if arg==gtk.RESPONSE_OK:
            page = self.notebook.get_current_page()
            for e in self.entrylists[page]:
                e.add_history(e.entry.get_text())
            paths = [ e.entry.get_text() or "" for e in self.entrylists[page] ]
            if page < 2 and not self.three_way_compare[page].get_active():
                paths.pop(0)
            methods = (self.parentapp.append_filediff,
                       self.parentapp.append_dirdiff,
                       self.parentapp.append_version )
            print "OK", page, paths
            methods[page](paths)
        self.toplevel.destroy()
        
################################################################################
#
# usage
#
################################################################################
usage_string = _("""Meld is a file and directory comparison tool. Usage:

    meld                        Start with no windows open
    meld <dir>                  Start with CVS browser in 'dir'
    meld <file>                 Start with CVS diff of 'file'
    meld <file> <file> [file]   Start with 2 or 3 way file comparison
    meld <dir>  <dir>  [dir]    Start with 2 or 3 way directory comparison

Options:
    -h, --help                  Show this help text and exit
    -v, --version               Display the version and exit

For more information choose help -> contents.
Report bugs at http://bugzilla.gnome.org/buglist.cgi?product=meld
Discuss meld at http://mail.gnome.org/mailman/listinfo/gnome-devtools
""")

version_string = _("""Meld %s
Written by Stephen Kennedy <stevek@gnome.org>""") % version

################################################################################
#
# Main
#
################################################################################
def main():
    import optparse

    class Unbuffered(object):
        def __init__(self, file):
            self.file = file
        def write(self, arg):
            self.file.write(arg)
            self.file.flush()
        def __getattr__(self, attr):
            return getattr(self.file, attr)
    sys.stdout = Unbuffered(sys.stdout)

    parser = optparse.OptionParser(usage=_("Usage: meld [options] [arguments]"), version=version_string)
    parser.add_option("-L", "--label", action="append", help=_("Use label instead of filename. This option may be used several times."))
    parser.add_option("-x", "--existing", action="store_true", help=_("Use an existing instance"))
    parser.add_option("-u", "--unified", action="store_true", help=_("Ignored for compatibility"))
    options, args = parser.parse_args()

    remote = None
    ok = False
    if options.existing:
        bus = dbus.SessionBus()
        remote_service = bus.get_service("org.gnome.meld")
        remote = remote_service.get_object("/App", "org.gnome.meld")
        ok = True

    if ok:
        app = remote
    else:
        try:
            service = dbus.Service("org.gnome.meld")
        except dbus.dbus_bindings.DBusException, e:
            service = None

        app = MeldApp( None )

    if len(args) == 0:
        pass

    elif len(args) == 1:
        a = args[0]
        if os.path.isfile(a):
            doc = cvsview.CvsView(app.prefs)
            def cleanup():
                app.scheduler.remove_scheduler(doc.scheduler)
            app.scheduler.add_task(cleanup)
            app.scheduler.add_scheduler(doc.scheduler)
            doc.set_location( os.path.dirname(a) )
            doc.connect("create-diff", lambda obj,arg: app.append_diff(arg) )
            doc.run_cvs_diff([a])
        else:
            app.append_version( [a] )
                
    elif len(args) in (2,3):
        app.append_diff( args )
    else:
        app.usage( _("Wrong number of arguments (Got %i)") % len(args))

    if not ok:
        app.main()

