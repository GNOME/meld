# Copyright (C) 2002-2009 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2010-2026 Kai Willadsen <kai.willadsen@gmail.com>
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

from typing import ClassVar

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk

from meld.conf import _
from meld.settings import settings

CONSTRUCT_FLAGS = GObject.ParamFlags.READWRITE | GObject.ParamFlags.CONSTRUCT_ONLY


class ColumnItem(GObject.Object):
    __gtype_name__ = "ColumnItem"

    column_name = GObject.Property(type=str, flags=CONSTRUCT_FLAGS)
    label = GObject.Property(type=str, flags=CONSTRUCT_FLAGS)
    active = GObject.Property(type=bool, default=False)


@Gtk.Template(resource_path="/org/gnome/meld/ui/column-list.ui")
class ColumnList(Gtk.Box):
    __gtype_name__ = "ColumnList"

    listbox = Gtk.Template.Child()
    row_menu = Gtk.Template.Child()

    available_columns: ClassVar[dict] = {
        "size": _("Size"),
        "modification time": _("Modification time"),
        "iso-time": _("Modification time (ISO)"),
        "permissions": _("Permissions"),
    }

    settings_key = GObject.Property(type=str, flags=CONSTRUCT_FLAGS)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Unwrap the saved (column-name, visibility) pairs
        column_vis = {}
        column_order = {}
        for sort_key, (name, visibility) in enumerate(
            settings.get_value(self.settings_key)
        ):
            column_vis[name] = bool(visibility)
            column_order[name] = sort_key

        ordered = sorted(
            self.available_columns.items(),
            key=lambda kv: column_order.get(kv[0], len(self.available_columns)),
        )

        self.model = Gio.ListStore.new(ColumnItem)
        for name, label in ordered:
            item = ColumnItem(
                column_name=name, label=label, active=column_vis.get(name, False)
            )
            item.connect("notify::active", self._update_columns)
            self.model.append(item)

        self.listbox.bind_model(self.model, self._create_row)
        self.model.connect("items-changed", self._update_action_states)
        self._update_action_states()

    def _create_row(self, item: ColumnItem):
        row = Adw.SwitchRow(title=item.label)
        row.item = item
        item.bind_property(
            "active",
            row,
            "active",
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
        )

        handle = Gtk.Image.new_from_icon_name("list-drag-handle-symbolic")
        row.add_prefix(handle)

        drag_source = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        drag_source.connect("prepare", self._on_drag_prepare, row)
        drag_source.connect("drag-begin", self._on_drag_begin, row)
        handle.add_controller(drag_source)

        drop_target = Gtk.DropTarget.new(Adw.SwitchRow, Gdk.DragAction.MOVE)
        drop_target.connect("drop", self._on_drop, row)
        row.add_controller(drop_target)

        actions = Gio.SimpleActionGroup()
        move_up = Gio.SimpleAction.new("move-up", None)
        move_up.connect("activate", self._on_move_up, row)
        actions.add_action(move_up)
        move_down = Gio.SimpleAction.new("move-down", None)
        move_down.connect("activate", self._on_move_down, row)
        actions.add_action(move_down)
        row.row_actions = actions

        menu_button = Gtk.MenuButton(
            icon_name="view-more-symbolic",
            menu_model=self.row_menu,
            valign=Gtk.Align.CENTER,
            tooltip_text=_("Column options"),
        )
        menu_button.add_css_class("flat")
        menu_button.insert_action_group("row", actions)
        row.add_suffix(menu_button)

        return row

    def _on_drag_prepare(self, source, x, y, row):
        value = GObject.Value(Adw.SwitchRow, row)
        return Gdk.ContentProvider.new_for_value(value)

    def _on_drag_begin(self, source, drag, row):
        source.set_icon(Gtk.WidgetPaintable.new(row), 0, 0)

    def _on_drop(self, target, source_row, x, y, target_row):
        self._move_item(source_row.item, target_row.get_index())
        return True

    def _on_move_up(self, action, param, row):
        self._move_item(row.item, row.get_index() - 1)

    def _on_move_down(self, action, param, row):
        self._move_item(row.item, row.get_index() + 1)

    def _move_item(self, item, position):
        found, current = self.model.find(item)
        if not found:
            return
        position = max(0, min(position, self.model.get_n_items() - 1))
        if position == current:
            return
        self.model.remove(current)
        self.model.insert(position, item)
        self._update_columns()

    def _update_action_states(self, *_args):
        count = self.model.get_n_items()
        for index in range(count):
            row = self.listbox.get_row_at_index(index)
            row.row_actions.lookup_action("move-up").set_enabled(index > 0)
            row.row_actions.lookup_action("move-down").set_enabled(index < count - 1)

    def _update_columns(self, *args):
        value = [(item.column_name.lower(), item.active) for item in self.model]
        settings.set_value(self.settings_key, GLib.Variant("a(sb)", value))
