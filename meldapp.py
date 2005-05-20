### Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>

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

# gtk
import gobject
import gtk

# project
import paths
import glade
import misc
import task
import stock
import filediff
import dirdiff
import wocoview
import prefs

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
          <separator/>
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
        glade.GtkApp.__init__(self, paths.share_dir("glade2/meldapp.glade"), "window")

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
        self.prefs = prefs.Preferences("/apps/meld")
        glade.tie_to_gconf("/apps/meld/state/app", self.toplevel)

        self.idle_hooked = 0
        self.scheduler = task.LifoScheduler()
        self.scheduler.connect("runnable", self.on_scheduler_runnable )
        self.toplevel.show()

        if dbus_service:
            dbus.Object.__init__(self, "/App", dbus_service,
                [self.action_about__activate,
                 self.save_snapshot] )

    def save_snapshot(self, message, filename, x=0, y=0, width=-1, height=-1):
        win = self.toplevel.window
        if width == -1:
            width = win.get_size()[0]
        if height == -1:
            height = win.get_size()[1]
        pix = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False, 8, width,height)
        pix.get_from_drawable( win, win.get_colormap(), x,y, 0,0, width,height )
        pix.save(filename, "png")

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
            gobject.idle_add( self.on_idle )

    #
    # General events and callbacks
    #
    def on_toplevel__delete_event(self, *extra):
        return self.action_quit__activate()

    def on_notebook__switch_page(self, notebook, page, which):
        get_doc = lambda i : notebook.get_nth_page(i).get_data("pyobject")
        if notebook.get_current_page() >= 0:
            old_doc = get_doc( notebook.get_current_page() )
            old_doc.on_container_switch_out_event(self.uimanager)
        newdoc = get_doc(which)
        nbl = self.notebook.get_tab_label( newdoc.toplevel )
        self.toplevel.set_title( nbl.label.get_text() + " - Meld")
        self._set_doc_status("")
        newdoc.on_container_switch_event(self.uimanager)
        self.scheduler.add_task( newdoc.scheduler )

    #
    # Response to contained page signals
    #
    def on_page_label_changed(self, component, text):
        nbl = self.notebook.get_tab_label( component.toplevel )
        nbl.set_text(text)
        self.toplevel.set_title(text + " - Meld")
        self.notebook.child_set_property(component.toplevel, "menu-label", text)

    def on_page_file_changed(self, srcpage, filename):
        """A page has changed a file.
        """
        for c in self.notebook.get_children():
            page = c.get_data("pyobject")
            if page != srcpage:
                page.on_container_file_changed(filename)

    def on_page_create_diff(self, srcpage, filenames):
        self.append_filediff(filenames)

    def on_page_status_changed(self, srcpage, status):
        self._set_doc_status(status)

    def on_page_closed(self, srcpage):
        self.remove_page(srcpage)


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
        prefs.PreferencesDialog(self)

    #
    # Help actions
    #
    def action_help_contents__activate(self, *extra):
        glade.url_show("ghelp:///"+os.path.abspath(paths.doc_dir("meld.xml") ))

    def action_reportbug__activate(self, *extra):
        glade.url_show("http://bugzilla.gnome.org/buglist.cgi?product=meld")

    def action_about__activate(self, *extra):
        dialog = gtk.AboutDialog()
        dialog.set_name("Meld")
        dialog.set_version(version)
        dialog.set_website("http://meld.sf.net")
        dialog.set_authors(["Stephen Kennedy <stevek@gnome.org>"])
        dialog.set_logo_icon_name("glade2/pixmaps/icon.png")
        dialog.run()
        dialog.destroy()

    #
    # Child page operations
    #
    def try_remove_page(self, page):
        """Remove a page if the doc allows it.
        """
        if page.on_container_delete_event() == gtk.RESPONSE_OK:
            self.remove_page(page)

    def remove_page(self, page):
        """Unconditionally remove a page.
        """
        page.on_container_switch_out_event(self.uimanager)
        self.scheduler.remove_scheduler( page.scheduler )
        self.toplevel.set_title("Meld")
        self._set_doc_status("")
        self.notebook.remove_page( self.notebook.page_num(page.toplevel) )

    def _append_page(self, page, icon):
        """Common page append code.
        """
        nbl = glade.CloseLabel(icon)
        nbl.connect("closed", lambda b: self.try_remove_page(page))
        self.notebook.append_page( page.toplevel, nbl)
        self.notebook.set_current_page( self.notebook.page_num(page.toplevel) )
        self.scheduler.add_scheduler(page.scheduler)
        page.connect("label-changed", self.on_page_label_changed)
        page.connect("file-changed", self.on_page_file_changed)
        page.connect("create-diff", self.on_page_create_diff )
        page.connect("status-changed", self.on_page_status_changed )
        page.connect("closed", self.on_page_closed )

    def append_dirdiff(self, dirs):
        assert len(dirs) in (1,2,3)
        doc = dirdiff.DirDiff(self.prefs, len(dirs))
        self._append_page(doc, stock.STOCK_DIRDIFF_ICON)
        doc.set_locations(dirs)

    def append_filediff(self, files):
        assert len(files) in (1,2,3)
        doc = filediff.FileDiff(self.prefs, len(files))
        self._append_page(doc, stock.STOCK_FILEDIFF_ICON)
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

    def append_woco(self, locations):
        assert len(locations) in (1,)
        location = locations[0]
        doc = wocoview.WocoView(self.prefs, self.uimanager)
        self._append_page(doc, stock.STOCK_WOCO_ICON)
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
                       self.parentapp.append_woco)
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
    parser.add_option("-s", "--snapshot", action="store", help=_("Save snapshot to file,x,y,w,h"))
    parser.add_option("-x", "--existing", action="store_true", help=_("Use an existing instance"))
    parser.add_option("-u", "--unified", action="store_true", help=_("Ignored for compatibility"))
    options, args = parser.parse_args()

    remote = None
    if options.existing:
        try:
            bus = dbus.SessionBus()
            remote_service = bus.get_service("org.gnome.meld")
            remote = remote_service.get_object("/App", "org.gnome.meld")
        except dbus.dbus_bindings.DBusException, e:
            print _("Connection to existing app failed: %s") % e
        if remote and options.snapshot: #XXX
            args = options.snapshot.split(",")
            args[1:] = [int(a) for a in args[1:]]
            remote.save_snapshot(*args)
            sys.exit(0)

    if remote:
        app = remote
    else:
        try:
            service = dbus.Service("org.gnome.meld")
        except dbus.dbus_bindings.DBusException, e:
            service = None
        app = MeldApp( service )

    if len(args) == 0:
        pass

    elif len(args) == 1:
        a = args[0]
        if os.path.isfile(a):
            doc = wocoview.WocoView(app.prefs, app.uimanager)
            def cleanup():
                app.scheduler.remove_scheduler(doc.scheduler)
            app.scheduler.add_task(cleanup)
            app.scheduler.add_scheduler(doc.scheduler)
            doc.set_location( os.path.dirname(a) )
            doc.connect("create-diff", lambda obj,arg: app.append_diff(arg) )
            doc.run_cvs_diff([a])
        else:
            app.append_woco( [a] )
                
    elif len(args) in (2,3):
        app.append_diff( args )
    else:
        app.usage( _("Wrong number of arguments (Got %i)") % len(args))

    if not remote:
        app.main()

