
TEST_REQUIRES = {
    "GLib": "2.0",
    "Gtk": "3.0",
    "GtkSource": "4",
}


def enforce_requires():
    import gi

    for namespace, version in TEST_REQUIRES.items():
        gi.require_version(namespace, version)


enforce_requires()
