
import os
import sys

__package__ = "meld"
__version__ = "3.16.0"

# START; these paths are clobbered on install by meld.build_helpers
DATADIR = os.path.join(sys.prefix, "share", "meld")
LOCALEDIR = os.path.join(sys.prefix, "share", "locale")
# END
UNINSTALLED = False

# Installed from main script
_ = lambda x: x
ngettext = lambda x, *args: x


def frozen():
    global DATADIR, LOCALEDIR

    try:
        from Foundation import NSBundle
        bundle = NSBundle.mainBundle()
        resource_path =  bundle.resourcePath().fileSystemRepresentation()
        bundle_path = bundle.bundlePath().fileSystemRepresentation()
        frameworks_path = bundle.privateFrameworksPath().fileSystemRepresentation()
        executable_path = bundle.executablePath().fileSystemRepresentation()
        etc_path = os.path.join(resource_path , "etc")
        lib_path = os.path.join(resource_path , "lib")
        share_path = os.path.join(resource_path , "share")

        # Default to Adwaita GTK Theme or override with user's environment var
        gtk_theme= os.environ.get('GTK_THEME', "Adwaita")
        os.environ['GTK_THEME'] = gtk_theme

        # Main libraries environment variables
        #dyld_library_path = os.environ.get('DYLD_LIBRARY_PATH', '').split(':')
        #dyld_library_path.insert(0, lib_path)
        #dyld_library_path.insert(1, frameworks_path)
        #os.environ['DYLD_LIBRARY_PATH'] = ':'.join(dyld_library_path)
        #print "DYLD_LIBRARY_PATH %s" % os.environ.get('DYLD_LIBRARY_PATH', '')

        # Glib and GI environment variables
        os.environ['GSETTINGS_SCHEMA_DIR'] = os.path.join(
                                    share_path, "glib-2.0")
        os.environ['GI_TYPELIB_PATH'] = os.path.join(
                                    lib_path, "girepository-1.0")

        # Avoid GTK warnings unless user specifies otherwise
        debug_gtk = os.environ.get('G_ENABLE_DIAGNOSTIC', "0")
        os.environ['G_ENABLE_DIAGNOSTIC'] = debug_gtk

        # GTK environment variables
        os.environ['GTK_DATA_PREFIX'] = resource_path
        os.environ['GTK_EXE_PREFIX'] = resource_path
        os.environ['GTK_PATH'] = resource_path

        # XDG environment variables
        os.environ['XDG_CONFIG_DIRS'] = os.path.join(etc_path, "xdg")
        os.environ['XDG_DATA_DIRS'] = ":".join((share_path,
                                            os.path.join(share_path, "meld")))

        # Pango environment variables
        os.environ['PANGO_RC_FILE'] = os.path.join(etc_path, "pango", "pangorc")
        os.environ['PANGO_SYSCONFDIR'] = etc_path
        os.environ['PANGO_LIBDIR'] = lib_path

        # Gdk environment variables
        os.environ['GDK_PIXBUF_MODULEDIR'] = os.path.join(
                                lib_path, "gdk-pixbuf-2.0", "2.10.0", "loaders")
        os.environ['GDK_RENDERING'] = "image"

        # Python environment variables
        os.environ['PYTHONHOME'] = resource_path
        original_python_path = os.environ.get('PYTHONPATH', "")
        python_path = ":".join((lib_path,
                        os.path.join(lib_path, "python", "lib-dynload"),
                        os.path.join(lib_path, "python"),
                        original_python_path))
        os.environ['PYTHONPATH'] = python_path

        # meld specific
        DATADIR = os.path.join(share_path, "meld")
        LOCALEDIR = os.path.join(share_path, "mo")

    except ImportError:
        print "frozen: ImportError"
        melddir = os.path.dirname(sys.executable)
        DATADIR = os.path.join(melddir, "share", "meld")
        LOCALEDIR = os.path.join(melddir, "share", "mo")

        # This first bit should be unnecessary, but some things (GTK icon theme
        # location, GSettings schema location) don't fall back correctly.
        data_dir = os.environ.get('XDG_DATA_DIRS', "/usr/local/share/:/usr/share/")
        data_dir = ":".join((melddir, data_dir))
        os.environ['XDG_DATA_DIRS'] = data_dir


def uninstalled():
    global DATADIR, LOCALEDIR, UNINSTALLED

    melddir = os.path.abspath(os.path.join(
        os.path.dirname(os.path.realpath(__file__)), ".."))

    DATADIR = os.path.join(melddir, "data")
    LOCALEDIR = os.path.join(melddir, "build", "mo")
    UNINSTALLED = True

    # This first bit should be unnecessary, but some things (GTK icon theme
    # location, GSettings schema location) don't fall back correctly.
    data_dir = os.environ.get('XDG_DATA_DIRS', "/usr/local/share/:/usr/share/")
    data_dir = ":".join((melddir, data_dir))
    os.environ['XDG_DATA_DIRS'] = data_dir

def is_darwin():
    return sys.platform == "darwin"
