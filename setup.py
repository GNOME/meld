#!/usr/bin/env python

from distutils.core import setup
import glob

from DistUtilsExtra.command import (
    build_extra, build_i18n, build_help)

import meld.conf

from meld.build_helpers import build_icons


setup(
    name=meld.conf.__package__,
    version=meld.conf.__version__,
    description='Visual diff and merge tool',
    author='Kai Willadsen',
    author_email='kai.willadsen@gmail.com',
    url='http://meldmerge.org',
    packages=[
        'meld',
        'meld.ui',
        'meld.util',
        'meld.vc',
    ],
    package_data={
        'meld.vc': ['README', 'COPYING', 'NEWS']
    },
    scripts=['bin/meld'],
    data_files=[
        ('share/man/man1',
         ['meld.1']
         ),
        ('share/doc/meld',
         ['COPYING', 'NEWS']
         ),
        ('share/meld/icons',
         glob.glob("data/icons/*.xpm") +
         glob.glob("data/icons/*.png") +
         glob.glob("data/icons/COPYING*")
         ),
        ('share/meld/ui',
         glob.glob("data/ui/*.ui") + glob.glob("data/ui/*.xml")
         ),
    ],
    cmdclass={
        "build": build_extra.build_extra,
        "build_i18n": build_i18n.build_i18n,
        "build_help": build_help.build_help,
        "build_icons": build_icons,
    }
)
