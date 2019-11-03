
from gi.repository import Gio


def replace_menu_section(menu: Gio.Menu, section: Gio.MenuItem):
    """Replaces an existing section in GMenu `menu` with `section`

    The sections are compared by their `id` attributes, with the
    matching section in `menu` being replaced by the passed `section`.

    If there is no section in `menu` that matches `section`'s `id`
    attribute, a ValueError is raised.
    """
    section_id = section.get_attribute_value("id").get_string()
    for idx in range(menu.get_n_items()):
        item_id = menu.get_item_attribute_value(idx, "id").get_string()
        if item_id == section_id:
            break
    else:
        # FIXME: Better exception
        raise ValueError("Section %s not found" % section_id)
    menu.remove(idx)
    menu.insert_item(idx, section)
