
from gi.repository import Gio


def get_menu_section_index_by_id(menu: Gio.Menu, section_id: str) -> int:
    for idx in range(menu.get_n_items()):
        id_attr = menu.get_item_attribute_value(idx, "id")
        item_id = id_attr.get_string() if id_attr else None
        if item_id == section_id:
            return idx
    else:
        raise ValueError("Section %s not found" % section_id)


def find_menu_section(menu: Gio.Menu, section_id: str) -> Gio.Menu:
    # The logic flow here looks weird because the GMenu API is weird.
    # We're checking IDs on an item, but then we need to iterate the
    # item links to get the actual submenu/section GMenu object, which
    # we then return if it matched the ID we checked earlier... or it
    # doesn't match the ID in which case we recurse.
    for idx in range(menu.get_n_items()):
        id_attr = menu.get_item_attribute_value(idx, "id")
        item_id = id_attr.get_string() if id_attr else None

        it = menu.iterate_item_links(idx)
        while it.next():
            submenu = it.get_value()
            if item_id == section_id:
                return submenu

            child = find_menu_section(submenu, section_id)
            if child:
                return child


def replace_menu_section(menu: Gio.Menu, section: Gio.MenuItem):
    """Replaces an existing section in GMenu `menu` with `section`

    The sections are compared by their `id` attributes, with the
    matching section in `menu` being replaced by the passed `section`.

    If there is no section in `menu` that matches `section`'s `id`
    attribute, a ValueError is raised.
    """
    section_id = section.get_attribute_value("id").get_string()
    idx = get_menu_section_index_by_id(menu, section_id)
    menu.remove(idx)
    menu.insert_item(idx, section)
