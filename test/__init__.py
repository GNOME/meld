
TEST_REQUIRES = {
    "GLib": "2.0",
    "Gtk": "4.0",
    "GtkSource": "5",
}


def enforce_requires():
    import gi

    for namespace, version in TEST_REQUIRES.items():
        gi.require_version(namespace, version)


enforce_requires()
