#!/usr/bin/env python3

import os
import sys
from compileall import compile_dir
from os import environ, path
from subprocess import call

if not environ.get('DESTDIR', ''):
    PREFIX = environ.get('MESON_INSTALL_PREFIX', '/usr/local')
    DATA_DIR = path.join(PREFIX, 'share')
    print('Updating icon cache...')
    call(['gtk-update-icon-cache', '-qtf', path.join(DATA_DIR, 'icons', 'hicolor')])
    print("Compiling new schemas")
    call(["glib-compile-schemas", path.join(DATA_DIR, 'glib-2.0', 'schemas')])
    print("Updating desktop database")
    call(["update-desktop-database", path.join(DATA_DIR, 'applications')])

# Byte-compilation is enabled by passing the site-packages path to this script
if len(sys.argv) > 1:
    print('Byte-compiling Python module...')
    destdir = os.getenv("DESTDIR", "")
    python_source_install_path = sys.argv[1]
    if destdir:
        # The install path here will be absolute, so we can't use join()
        install_path = destdir + os.path.sep + python_source_install_path
    else:
        install_path = python_source_install_path
    compile_dir(os.path.join(install_path, "meld"), optimize=1)
