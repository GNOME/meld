# -*- coding: utf-8 -*-

#!/usr/bin/env python

import glob
import os
import site
from setuptools import setup
import meld.meldapp

APP_NAME = 'MeldMerge'
VERSION_STRING = '1.0'
FORCE_32_BIT = False

PLIST = {
    'CFBundleDocumentTypes': [
        {
            'CFBundleTypeExtensions': ['scmdifftool'],
            'CFBundleTypeIconFile': 'DiffToolDocument',
            'CFBundleTypeName': 'Diff Tool',
            'CFBundleTypeRole': 'Editor',
            'LSTypeIsPackage': True,
        },
    ],
    'CFBundleIdentifier': 'org.gnome.meld',
    'CFBundleShortVersionString': VERSION_STRING,
    'CFBundleSignature': '???',
    'CFBundleVersion': VERSION_STRING,
    'LSPrefersPPC': FORCE_32_BIT,
    'NSHumanReadableCopyright': u'Copyright © 2016',
    'CFBundleDisplayName': 'Meld',
    'CFBundleName': 'Meld',
    'NSHighResolutionCapable': True,
    'LSApplicationCategoryType': 'public.app-category.productivity',
    'LSRequiresNativeExecution': True,
}

#find_packages(exclude=["*.tests", "*.tests.*", "tests.*", "tests"])

setup(
    name="meldmerge",
    version="1.8.2",
    description='Visual diff and merge tool',
    author='The Meld project',
    author_email='meld-list@gnome.org',
    maintainer='Kai Willadsen',
    url='http://meldmerge.org',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: X11 Applications :: GTK',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)',
        'Programming Language :: Python',
        'Topic :: Desktop Environment :: Gnome',
        'Topic :: Software Development',
        'Topic :: Software Development :: Version Control',
    ],
    packages=[
        'meld',
        'meld.ui',
        'meld.util',
        'meld.vc',
    ],
    package_data={
        'meld': ['README', 'COPYING', 'NEWS'],
        'meld.vc': ['README', 'COPYING'],
    },
    app=['bin/meld'],
    setup_requires=["py2app"],
    options={'py2app': {
                "packages": ["gio", "gobject", "gtk", "cairo"],
                "includes": ["atk", "pango", "pangocairo"],
                'argv_emulation': True,
                'iconfile': 'osx/meld.icns',
                'plist': PLIST,
                'prefer_ppc': False,
    }},
    data_files=[
        ('share/man/man1',
         ['meld.1']
         ),
        ('share/doc/meld',
         ['COPYING', 'NEWS']
         ),
        ('share/meld',
         ['data/gschemas.compiled']
         ),
         ('share/meld',
          ['data/org.gnome.meld.gschema.xml']
          ),
        ('share/meld',
         ['data/meld.css']
         ),
        ('share/meld/icons',
         glob.glob("data/icons/*.png") +
         glob.glob("data/icons/COPYING*")
         ),
        ('share/meld/ui',
         glob.glob("data/ui/*.ui") + glob.glob("data/ui/*.xml")
         ),
    ],
)
