
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import GtkSource

from meld.conf import _
from meld.ui.listselector import FilteredListSelector, with_template_file


@with_template_file('encoding-selector.ui')
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


# TODO: When there's proper pygobject support for widget templates,
# make both selectors here use a generic UI file. We can't do this
# currently due to subclassing issues.

@with_template_file('language-selector.ui')
class SourceLangSelector(FilteredListSelector, Gtk.Grid):
    # The subclassing here is weird; the Selector must directly
    # subclass Gtk.Grid, or the template building explodes.

    __gtype_name__ = "SourceLangSelector"

    __gsignals__ = {
        'language-selected': (
            GObject.SignalFlags.RUN_FIRST | GObject.SignalFlags.ACTION,
            None, (GtkSource.Language,)),
    }

    # These exist solely to make subclassing easier.
    value_accessor = 'get_id'
    change_signal_name = 'language-selected'

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
