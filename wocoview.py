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

#import tempfile
import gobject
#import shutil
#import time
#import copy
import gtk
#import os
#import re

#import misc
import glade
import melddoc
import paths
import stock
import woco
#iimport tree
import wocotree

################################################################################
#
# WocoView
#
################################################################################
class WocoView(melddoc.MeldDoc, glade.Component):

    UI_DEFINITION = """
    <ui>
      <menubar name="MenuBar">
        <menu action="file_menu">
          <placeholder name="file_extras">
            <menuitem action="close"/>
          </placeholder>
        </menu>
        <placeholder name="menu_extras">
          <menu action="version_menu">
            <menuitem action="diff"/>
            <separator/>
            <menuitem action="update"/>
            <menuitem action="commit"/>
            <menuitem action="add"/>
            <menuitem action="remove"/>
            <menuitem action="delete"/>
          </menu>
          <menu action="view_menu">
            <menuitem action="view_up"/>
            <menuitem action="view_down"/>
            <separator/>
            <menuitem action="flatten"/>
            <separator/>
            <menuitem action="view_modified"/>
            <menuitem action="view_normal"/>
            <menuitem action="view_unknown"/>
            <menuitem action="view_ignored"/>
            <separator/>
            <menuitem action="view_console"/>
          </menu>
        </placeholder>
      </menubar>
      <toolbar name="ToolBar">
          <toolitem action="diff"/>
          <separator/>
          <toolitem action="flatten"/>
          <toolitem action="view_modified"/>
          <toolitem action="view_normal"/>
          <toolitem action="view_unknown"/>
          <toolitem action="view_ignored"/>
          <separator/>
          <toolitem action="update"/>
          <toolitem action="commit"/>
          <toolitem action="add"/>
          <toolitem action="remove"/>
          <toolitem action="delete"/>
      </toolbar>
    </ui>
    """

    UI_ACTIONS = (
        ('file_menu', None, _('_File')),
            ('close', gtk.STOCK_CLOSE,
                _('_Close'), '<Control>w', _('Close this tab')),
        ('version_menu', None, _('_Version')),
            ('diff', stock.STOCK_VERSION_DIFF,
                _('_Diff'), None, _('Compare versions')),
            ('update', stock.STOCK_VERSION_UPDATE,
                _('_Update'), None, _('Update the local copy')),
            ('commit', stock.STOCK_VERSION_COMMIT,
                _('_Commit'), None, _('Commit changes')),
            ('add', stock.STOCK_VERSION_ADD,
                _('_Add'), None, _('Add to control')),
            ('remove', stock.STOCK_VERSION_REMOVE,
                _('_Remove'), None, _('Remove from control')),
            ('delete', gtk.STOCK_DELETE,
                _('_Delete'), None, _('Remove locally')),

        ('view_menu', None, _('_View')),
            ('view_up', gtk.STOCK_GO_UP,
                _('_Up'), '<Control>e', _('Previous change')),
            ('view_down', gtk.STOCK_GO_DOWN,
                _('_Down'), '<Control>d', _('Next change')),
            ('flatten', gtk.STOCK_GOTO_BOTTOM,
                _('_Flatten'), None, _('Flatten tree'), False),
            ('view_modified', stock.STOCK_FILTER_MODIFIED,
                _('_Modified'), None, _('View modified files'), True),
            ('view_normal', stock.STOCK_FILTER_NORMAL,
                _('_Normal'), None, _('View normal files'), False),
            ('view_unknown', stock.STOCK_FILTER_UNKNOWN,
                _('Un_known'), None, _('View non version controlled files'), False),
            ('view_ignored', stock.STOCK_FILTER_IGNORED,
                _('_Ignored'), None, _('View ignored items'), False),
            ('view_console', None,
                _('_Console'), None, _('View command line output'), False),
    )

    class DirectoryBrowser(glade.Component):
        def __init__(self, parent):
            glade.Component.__init__(self, paths.share_dir("glade2/wocoview.glade"), "dirchooserdialog")
            self.parent = parent
            self.toplevel.set_transient_for(self.parent.toplevel.get_toplevel())
            self.connect_signal_handlers()
        def on_toplevel__response(self, dialog, arg):
            if arg == gtk.RESPONSE_OK:
                self.parent.set_location( dialog.get_filename() )
            self.toplevel.destroy()


    def __init__(self, prefs, uimanager):
        melddoc.MeldDoc.__init__(self, prefs)
        glade.Component.__init__(self, paths.share_dir("glade2/wocoview.glade"), "wocoview")

        self.actiongroup = gtk.ActionGroup("WocoActions")
        self.add_actions( self.actiongroup, self.UI_ACTIONS )
        uimanager.insert_action_group(self.actiongroup, 1)
        self.ui_merge_id = uimanager.add_ui_from_string(self.UI_DEFINITION)

        self.tempfiles = []
        self.model = wocotree.Tree()
        self.treeview.set_model(self.model)
        self.treeview.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        self.treeview.set_headers_visible(1)
        column = gtk.TreeViewColumn( _("Name") )
        renpix = gtk.CellRendererPixbuf()
        rentext = gtk.CellRendererText()
        column.pack_start(renpix, expand=0)
        column.pack_start(rentext, expand=1)
        column.set_attributes(renpix, pixbuf=self.model.column_index(tree.COL_ICON, 0))
        column.set_attributes(rentext, markup=self.model.column_index(tree.COL_TEXT, 0))
        self.treeview.append_column(column)

        def addCol(name, num):
            column = gtk.TreeViewColumn(name)
            rentext = gtk.CellRendererText()
            column.pack_start(rentext, expand=0)
            column.set_attributes(rentext, markup=self.model.column_index(num, 0))
            self.treeview.append_column(column)
            return column

        self.treeview_column_location = addCol( _("Location"), COL_LOCATION)
        addCol(_("Status"), COL_STATUS)
        addCol(_("Rev"), COL_REVISION)
        addCol(_("Tag"), COL_TAG)
        addCol(_("Options"), COL_OPTIONS)

        class ConsoleStream(object):
            def __init__(this, textview):
                this.textview = textview
                b = textview.get_buffer()
                this.mark = b.create_mark("END", b.get_end_iter(), 0)
            def write(this, s):
                if s:
                    b = this.textview.get_buffer()
                    b.insert(b.get_end_iter(), s)
                    this.textview.scroll_mark_onscreen( this.mark )
        self.consolestream = ConsoleStream(self.consoleview)
        self.location = None
        toolbuttons = [(uimanager.get_widget("/ToolBar/%s"%w),w) for w in
            "flatten view_modified view_normal view_unknown view_ignored".split() ]
        self.treeview_column_location.set_visible( not self.action_flatten.get_active() )
        self.action_view_console__toggled(self.action_view_console)
        self.connect_signal_handlers()
        glade.tie_to_gconf("/apps/meld/state/woco", *toolbuttons)

    def action_close__activate(self, object):
        self.emit("closed")

    def action_diff__activate(self, object):
        files = self._get_selected_files()
        if len(files):
            self.run_cvs_diff(files, empty_patch_ok=1)

    def action_flatten__toggled(self, button):
        self.treeview_column_location.set_visible( not self.action_flatten.get_active() )
        self.refresh()

    def action_commit__activate(self, object):
        dialog = CommitDialog( self )
        dialog.run()

    def action_update__activate(self, object):
        self._command_on_selected( self.prefs.get_cvs_command("update") )

    def action_add__activate(self, object):
        self._command_on_selected(self.prefs.get_cvs_command("add") )

    def action_remove__activate(self, object):
        self._command_on_selected(self.prefs.get_cvs_command("rm") + ["-f"] )

    def action_delete__activate(self, object):
        files = self._get_selected_files()
        for name in files:
            try:
                if os.path.isfile(name):
                    os.remove(name)
                elif os.path.isdir(name):
                    if misc.run_dialog(_("'%s' is a directory.\nRemove recusively?") % os.path.basename(name),
                            parent = self,
                            buttonstype=gtk.BUTTONS_OK_CANCEL) == gtk.RESPONSE_OK:
                        shutil.rmtree(name)
            except OSError, e:
                misc.run_dialog(_("Error removing %s\n\n%s.") % (name,e), parent = self)
        workdir = _commonprefix(files)
        self.refresh_partial(workdir)

    def action_view_modified__toggled(self,*args):
        self.refresh()

    def action_view_normal__toggled(self,*args):
        self.refresh()

    def action_view_unknown__toggled(self,*args):
        self.refresh()

    def action_view_ignored__toggled(self,*args):
        self.refresh()

    def action_view_up__activate(self):
        self.action_view_go(gtk.gdk.SCROLL_UP)

    def action_view_down__activate(self):
        self.action_view_go(gtk.gdk.SCROLL_DOWN)

    def action_view_go__activate(self, direction):
        start_iter = self.model.get_iter( (self._get_selected_treepaths() or [(0,)])[-1] )
        def goto_iter(it):
            curpath = self.model.get_path(it)
            for i in range(len(curpath)-1):
                self.treeview.expand_row( curpath[:i+1], 0)
            self.treeview.set_cursor(curpath)
        search = {gtk.gdk.SCROLL_UP : self.model.inorder_search_up}.get(direction, self.model.inorder_search_down)
        for it in search( start_iter ):
            state = int(self.model.get_state( it, 0))
            if state not in (tree.STATE_NORMAL, tree.STATE_EMPTY):
                goto_iter(it)
                return

    def action_view_console__toggled(self, toggle):
        if toggle.get_active():
            self.prefs.cvs_console_visible = 1
            self.console_hbox.show()
            self.console_show_box.hide()
        else:
            self.prefs.cvs_console_visible = 0
            self.console_hbox.hide()
            self.console_show_box.show()


gobject.type_register(WocoView)
