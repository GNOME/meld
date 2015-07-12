#!/usr/bin/env python

import glob
import os
import site

from cx_Freeze import setup, Executable

import meld.build_helpers
import meld.conf

site_dir = site.getsitepackages()[1]
include_dll_path = os.path.join(site_dir, "gnome")

missing_dll = [
    'libgtk-3-0.dll',
    'libgdk-3-0.dll',
    'libatk-1.0-0.dll',
    'libintl-8.dll',
    'libzzz.dll',
    'libwinpthread-1.dll',
    'libcairo-gobject-2.dll',
    'libgdk_pixbuf-2.0-0.dll',
    'libpango-1.0-0.dll',
    'libpangocairo-1.0-0.dll',
    'libpangoft2-1.0-0.dll',
    'libpangowin32-1.0-0.dll',
    'libffi-6.dll',
    'libfontconfig-1.dll',
    'libfreetype-6.dll',
    'libgio-2.0-0.dll',
    'libglib-2.0-0.dll',
    'libgmodule-2.0-0.dll',
    'libgobject-2.0-0.dll',
    'libgirepository-1.0-1.dll',
    'libgtksourceview-3.0-1.dll',
    'libjasper-1.dll',
    'libjpeg-8.dll',
    'libpng16-16.dll',
    'libgnutls-26.dll',
    'libxmlxpat.dll',
    'librsvg-2-2.dll',
    'libharfbuzz-gobject-0.dll',
    'libwebp-5.dll',
]

gtk_libs = [
    'etc/fonts',
    'etc/gtk-3.0/settings.ini',
    'etc/pango',
    'lib/gdk-pixbuf-2.0',
    'lib/girepository-1.0',
    'share/fontconfig',
    'share/fonts',
    'share/glib-2.0',
    'share/gtksourceview-3.0',
    'share/icons',
]

include_files = [(os.path.join(include_dll_path, path), path) for path in
                 missing_dll + gtk_libs]

build_exe_options = {
    "compressed": False,
    "icon": "data/icons/meld.ico",
    "includes": ["gi"],
    "packages": ["gi", "weakref"],
    "include_files": include_files,
}


# Create our registry key, and fill with install directory and exe
registry_table = [
    ('MeldKLM', 2, 'SOFTWARE\Meld', '*', None, 'TARGETDIR'),
    ('MeldInstallDir', 2, 'SOFTWARE\Meld', 'InstallDir', '[TARGETDIR]', 'TARGETDIR'),
    ('MeldExecutable', 2, 'SOFTWARE\Meld', 'Executable', '[TARGETDIR]Meld.exe', 'TARGETDIR'),
]

# Provide the locator and app search to give MSI the existing install directory
# for future upgrades
reg_locator_table = [
    ('MeldInstallDirLocate', 2, 'SOFTWARE\Meld', 'InstallDir', 0)
]
app_search_table = [('TARGETDIR', 'MeldInstallDirLocate')]

msi_data = {
    'Registry': registry_table,
    'RegLocator': reg_locator_table,
    'AppSearch': app_search_table
}

bdist_msi_options = {
    "upgrade_code": "{1d303789-b4e2-4d6e-9515-c301e155cd50}",
    "data": msi_data,
}


setup(
    name="Meld",
    version=meld.conf.__version__,
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
    options = {
        "build_exe": build_exe_options,
        "bdist_msi": bdist_msi_options,
    },
    executables = [
        Executable(
            "bin/meld",
            base="Win32GUI",
            targetName="Meld.exe",
            shortcutName="Meld",
            shortcutDir="ProgramMenuFolder",
        ),
    ],
    packages=[
        'meld',
        'meld.ui',
        'meld.util',
        'meld.vc',
    ],
    package_data={
        'meld': ['README', 'COPYING', 'NEWS']
    },
    scripts=['bin/meld'],
    data_files=[
        ('share/man/man1',
         ['meld.1']
         ),
        ('share/doc/meld-' + meld.conf.__version__,
         ['COPYING', 'NEWS']
         ),
        ('share/meld',
         ['data/meld.css', 'data/meld-dark.css']
         ),
        ('share/meld/icons',
         glob.glob("data/icons/*.png") +
         glob.glob("data/icons/COPYING*")
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
    }
)
