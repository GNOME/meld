
from gi.repository import GLib
from gi.repository import Gtk

from meld.conf import ui_file


def with_template_file(template_file):
    """Class decorator for setting a widget template"""

    def add_template(cls):
        template_path = ui_file(template_file)
        template = open(template_path, 'rb').read()
        template_bytes = GLib.Bytes.new(template)
        cls.set_template(template_bytes)
        return cls

    return add_template


class TemplateHackMixin:

    def get_template_child(self, widget_type, name):
        # Taken from an in-progress patch on bgo#701843

        def get_template_child(widget, widget_type, name):
            # Explicitly use gtk_buildable_get_name() because it is masked by
            # gtk_widget_get_name() in GI.
            if isinstance(widget, widget_type) and \
                    isinstance(widget, Gtk.Buildable) and \
                    Gtk.Buildable.get_name(widget) == name:
                return widget

            if isinstance(widget, Gtk.Container):
                for child in widget.get_children():
                    result = get_template_child(child, widget_type, name)
                    if result is not None:
                        return result

        return get_template_child(self, widget_type, name)


class FilteredListSelector(TemplateHackMixin):

    # FilteredListSelector was intially based on gedit's
    # GeditHighlightModeSelector
    # Copyright (C) 2013 - Ignacio Casal Quinteiro
    # Python translation and adaptations
    # Copyright (C) 2015, 2017 Kai Willadsen <kai.willadsen@gmail.com>

    __gtype_name__ = 'FilteredListSelector'

    NAME_COLUMN, VALUE_COLUMN = 0, 1

    def __init__(self):
        Gtk.Grid.__init__(self)
        self.init_template()

        self.entry = self.get_template_child(Gtk.SearchEntry, 'entry')
        self.treeview = self.get_template_child(Gtk.TreeView, 'treeview')
        self.treeview_selection = self.treeview.get_selection()
        # FIXME: Should be able to access as a template child, but can't.
        self.listfilter = self.treeview.get_model()
        self.liststore = self.listfilter.get_model()

        self.populate_model()
        self.filter_string = ''
        self.entry.connect('changed', self.on_entry_changed)
        self.listfilter.set_visible_func(self.name_filter)

        self.entry.connect('activate', self.on_activate)
        self.treeview.connect('row-activated', self.on_activate)

    def populate_model(self):
        raise NotImplementedError

    def select_value(self, value):
        if not value:
            return

        new_value_getter = getattr(value, self.value_accessor)
        for row in self.liststore:
            row_value = row[self.VALUE_COLUMN]
            if not row_value:
                continue
            old_value_getter = getattr(row_value, self.value_accessor)
            if old_value_getter() != new_value_getter():
                continue
            self.treeview_selection.select_path(row.path)
            self.treeview.scroll_to_cell(row.path, None, True, 0.5, 0)

    def name_filter(self, model, it, *args):
        if not self.filter_string:
            return True
        name = model.get_value(it, self.NAME_COLUMN).lower()
        return self.filter_string.lower() in name

    def on_entry_changed(self, entry):
        self.filter_string = entry.get_text()
        self.listfilter.refilter()
        first = self.listfilter.get_iter_first()
        if first:
            self.treeview_selection.select_iter(first)

    def on_activate(self, *args):
        model, it = self.treeview_selection.get_selected()
        if not it:
            return
        value = model.get_value(it, self.VALUE_COLUMN)
        self.emit(self.change_signal_name, value)
