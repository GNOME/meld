
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import GtkSource

from meld.conf import _
from meld.ui._gtktemplate import Template
from meld.ui.listselector import FilteredListSelector

# TODO: Current pygobject support for templates excludes subclassing of
# templated classes, which is why we have two near-identical UI files
# here, and why we can't subclass Gtk.Grid directly in
# FilteredListSelector.

# The subclassing here is weird; the Selector must directly subclass
# Gtk.Grid; we can't do this on the FilteredListSelector. Likewise, the
# Template.Child attributes must be per-class, because of how they're
# registered by the templating engine.


@Template(resource_path='/org/gnome/meld/ui/encoding-selector.ui')
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

    entry = Template.Child('entry')
    treeview = Template.Child('treeview')

    def populate_model(self):
        for enc in GtkSource.Encoding.get_all():
            self.liststore.append((self.get_value_label(enc), enc))

    def get_value_label(self, enc):
        return _('{name} ({charset})').format(
            name=enc.get_name(), charset=enc.get_charset())


# SourceLangSelector was intially based on gedit's
# GeditHighlightModeSelector
# Copyright (C) 2013 - Ignacio Casal Quinteiro
# Python translation and adaptations
# Copyright (C) 2015, 2017 Kai Willadsen <kai.willadsen@gmail.com>


@Template(resource_path='/org/gnome/meld/ui/language-selector.ui')
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

    entry = Template.Child('entry')
    treeview = Template.Child('treeview')

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
