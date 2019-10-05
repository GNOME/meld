
from gi.repository import GObject, Gtk, GtkSource

from meld.conf import _

# TODO: Current pygobject support for templates excludes subclassing of
# templated classes, which is why we have two near-identical UI files
# here, and why we can't subclass Gtk.Grid directly in
# FilteredListSelector.


class FilteredListSelector:

    # FilteredListSelector was initially based on gedit's
    # GeditHighlightModeSelector
    # Copyright (C) 2013 - Ignacio Casal Quinteiro
    # Python translation and adaptations
    # Copyright (C) 2015, 2017 Kai Willadsen <kai.willadsen@gmail.com>

    __gtype_name__ = 'FilteredListSelector'

    NAME_COLUMN, VALUE_COLUMN = 0, 1

    def __init__(self):
        super().__init__()

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


# The subclassing here is weird; the Selector must directly subclass
# Gtk.Grid; we can't do this on the FilteredListSelector. Likewise, the
# Gtk.Template.Child attributes must be per-class, because of how
# they're registered by the templating engine.


@Gtk.Template(resource_path='/org/gnome/meld/ui/encoding-selector.ui')
class EncodingSelector(FilteredListSelector, Gtk.Grid):
    # The subclassing here is weird; the Selector must directly
    # subclass Gtk.Grid, or the template building explodes.

    __gtype_name__ = 'EncodingSelector'

    __gsignals__ = {
        'encoding-selected': (
            GObject.SignalFlags.RUN_FIRST | GObject.SignalFlags.ACTION,
            None, (GtkSource.Encoding,)),
    }

    # These exist solely to make subclassing easier.
    value_accessor = 'get_charset'
    change_signal_name = 'encoding-selected'

    entry = Gtk.Template.Child('entry')
    treeview = Gtk.Template.Child('treeview')

    def populate_model(self):
        for enc in GtkSource.Encoding.get_all():
            self.liststore.append((self.get_value_label(enc), enc))

    def get_value_label(self, enc):
        return _('{name} ({charset})').format(
            name=enc.get_name(), charset=enc.get_charset())


# SourceLangSelector was initially based on gedit's
# GeditHighlightModeSelector
# Copyright (C) 2013 - Ignacio Casal Quinteiro
# Python translation and adaptations
# Copyright (C) 2015, 2017 Kai Willadsen <kai.willadsen@gmail.com>


@Gtk.Template(resource_path='/org/gnome/meld/ui/language-selector.ui')
class SourceLangSelector(FilteredListSelector, Gtk.Grid):

    __gtype_name__ = "SourceLangSelector"

    __gsignals__ = {
        'language-selected': (
            GObject.SignalFlags.RUN_FIRST | GObject.SignalFlags.ACTION,
            None, (GtkSource.Language,)),
    }

    # These exist solely to make subclassing easier.
    value_accessor = 'get_id'
    change_signal_name = 'language-selected'

    entry = Gtk.Template.Child('entry')
    treeview = Gtk.Template.Child('treeview')

    def populate_model(self):
        self.liststore.append((_("Plain Text"), None))
        manager = GtkSource.LanguageManager.get_default()
        for lang_id in manager.get_language_ids():
            lang = manager.get_language(lang_id)
            self.liststore.append((lang.get_name(), lang))

    def get_value_label(self, lang):
        if not lang:
            return _("Plain Text")
        return lang.get_name()
