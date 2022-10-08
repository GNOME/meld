#!/usr/bin/env python3

import sys
from compileall import compile_dir
from os import path

# Byte-compilation is enabled by passing the site-packages path to this script
if len(sys.argv) > 1:
    print('Byte-compiling Python module...')
    python_source_install_path = sys.argv[1]
    compile_dir(path.join(python_source_install_path, 'meld'), optimize=1)
