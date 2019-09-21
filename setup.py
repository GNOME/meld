#!/usr/bin/env python3

import glob
import sys
from distutils.core import setup

import meld.build_helpers
import meld.conf

if sys.version_info[:2] < meld.conf.PYTHON_REQUIREMENT_TUPLE:
    version = ".".join(map(str, meld.conf.PYTHON_REQUIREMENT_TUPLE))
    raise Exception("Meld setup requires Python %s or higher." % version)

setup(
    name=meld.conf.__package__,
    version=meld.conf.__version__,
    description='Visual diff and merge tool',
    author='Kai Willadsen',
    author_email='kai.willadsen@gmail.com',
    url='http://meldmerge.org',
    license='GPLv2+',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: X11 Applications :: GTK',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: Desktop Environment :: Gnome',
        'Topic :: Software Development',
        'Topic :: Software Development :: Version Control',
    ],
    keywords=['diff', 'merge'],
    packages=[
        'meld',
        'meld.matchers',
        'meld.ui',
        'meld.vc',
    ],
    package_data={
        'meld': ['README', 'COPYING', 'NEWS'],
        'meld.vc': ['README', 'COPYING'],
    },
    scripts=['bin/meld'],
    data_files=[
        ('share/man/man1',
         ['data/meld.1']
         ),
        ('share/doc/meld-' + meld.conf.__version__,
         ['COPYING', 'NEWS']
         ),
        ('share/meld',
         ['data/meld.css']
         ),
        ('share/meld/icons',
         glob.glob("data/icons/*.png") +
         glob.glob("data/icons/COPYING*")
         ),
        ('share/meld/styles',
         glob.glob("data/styles/*.xml")
         ),
        ('share/meld/ui',
         glob.glob("data/ui/*.ui") + glob.glob("data/ui/*.xml")
         ),
    ],
    cmdclass={
        "build_i18n": meld.build_helpers.build_i18n,
        "build_help": meld.build_helpers.build_help,
        "build_icons": meld.build_helpers.build_icons,
        "build_data": meld.build_helpers.build_data,
        "build_py": meld.build_helpers.build_py,
        "install": meld.build_helpers.install,
        "install_data": meld.build_helpers.install_data,
    },
    distclass=meld.build_helpers.MeldDistribution,
)
