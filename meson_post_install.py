#!/usr/bin/env python3

import os
import sys
from compileall import compile_dir

# Byte-compilation is enabled by passing the site-packages path to this script
if len(sys.argv) > 1:
    print("Byte-compiling Python module...")
    destdir = os.getenv("DESTDIR", "")
    python_source_install_path = sys.argv[1]
    if destdir:
        # The install path here will be absolute, so we can't use join()
        install_path = destdir + os.path.sep + python_source_install_path
    else:
        install_path = python_source_install_path
    compile_dir(os.path.join(install_path, "meld"), optimize=1)
