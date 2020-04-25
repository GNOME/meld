#!/usr/bin/env python3

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
    python_source_install_path = sys.argv[1]
    compile_dir(path.join(python_source_install_path, 'meld'), optimize=1)
