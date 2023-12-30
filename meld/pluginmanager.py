import enum
import sys

from gi.repository import Gio, GObject, Peas, PeasGtk

from meld.confshim import get_meld_paths
from meld.menuhelpers import find_menu_section
from meld.settings import plugin_settings


class PluginMenu(enum.Enum):
    app_comparison = "meld-plugin-comparison-menu"


class API(GObject.GObject):

    plugin_menus: dict[str, Gio.MenuModel]

    def __init__(self, app):
        GObject.GObject.__init__(self)
        self.app = app
        self._plugin_menus = {}

    def _get_plugin_menu(self, plugin_menu: PluginMenu) -> Gio.MenuModel:
        if plugin_menu not in self._plugin_menus:
            main_menu = self.app.get_menu_by_id("gear-menu")
            menu = find_menu_section(main_menu, plugin_menu.value)
            if not menu:
                raise KeyError(f"No menu with ID {plugin_menu.value}")
            self._plugin_menus[plugin_menu] = menu

        return self._plugin_menus[plugin_menu]

    def add_menu_item(
        self, plugin_menu: PluginMenu, item_id: str, item: Gio.MenuItem
    ) -> None:
        item.set_attribute([("meld-plugin-item-id", "s", item_id)])
        menu = self._get_plugin_menu(plugin_menu)
        menu.append_item(item)

    def remove_menu_item(self, plugin_menu: PluginMenu, item_id: str) -> None:
        menu = self._get_plugin_menu(plugin_menu)

        for idx in range(menu.get_n_items()):
            menu_id = menu.get_item_attribute(idx, "meld-plugin-item-id").get_string()
            if item_id == menu_id:
                menu.remove(item_id)
                return


class PluginManager:
    def __init__(self, app):
        # Make sure we have the plugin manager loaded, or the preferences
        # dialog will fail to construct properly.
        GObject.type_ensure(PeasGtk.PluginManager)

        self.app = app
        self.engine = Peas.Engine.get_default()
        self.engine.enable_loader("python3")

        # Set up plugin search paths
        meld_paths = get_meld_paths()
        self.engine.add_search_path(
            str(meld_paths.user_plugins_dir),
            str(meld_paths.user_plugins_data_dir),
        )
        self.engine.add_search_path(
            str(meld_paths.system_plugins_dir),
            str(meld_paths.system_plugins_data_dir),
        )

        # Plugin initialisation changes sys.argv, so we copy and restore it
        # here.
        argv = sys.argv[:]

        api = API(self.app)
        self.extension_set = Peas.ExtensionSet.new(
            self.engine, Peas.Activatable, ["object"], [api]
        )
        self.extension_set.connect("extension-added", self.on_extension_added)
        self.extension_set.connect("extension-removed", self.on_extension_removed)

        self._wait_for_window = self.app.connect("window-added", self.on_window_added)
        self._pending_extensions = []

        # Bind our active-plugins config to the engine, and rely upon it
        # to load plugins appropriately.
        plugin_settings.bind(
            "active-plugins",
            self.engine,
            "loaded-plugins",
            Gio.SettingsBindFlags.DEFAULT,
        )

        sys.argv = argv

    def on_extension_added(
        self,
        extension_set: Peas.ExtensionSet,
        plugin_info: Peas.PluginInfo,
        extension: Peas.ExtensionBase,
    ) -> bool:
        # If we don't yet have a window, queue extension initialization
        # until we do.
        if self._wait_for_window:
            self._pending_extensions.append(extension)
        else:
            extension.activate()

    def on_extension_removed(
        self,
        extension_set: Peas.ExtensionSet,
        plugin_info: Peas.PluginInfo,
        extension: Peas.ExtensionBase,
    ) -> bool:
        extension.deactivate()

    def on_window_added(self, app, window):
        # Activate any pending extensions and clear the signal handler
        self.app.disconnect(self._wait_for_window)

        for extension in self._pending_extensions:
            extension.activate()
        self._pending_extensions = []
