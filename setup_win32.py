#!/usr/bin/env python3

import glob
import os.path
import platform
import sys
import sysconfig

from cx_Freeze import Executable, setup

import meld.build_helpers
import meld.conf


def get_non_python_dependencies():
    """Returns list of tuples containing extra dependencies required to run
    meld on current platform.
    Every pair corresponds to a single required file/folder.
    First tuple item correspond to path expected in meld installation
    relative to meld prefix.
    Second tuple item is path in local filesystem during build.
    Note that for returned dynamic libraries their dependencies
    are expected to be resolved by caller, for example by cx_freeze.
    """
    gtk_prefix = sys.prefix
    gtk_exec_prefix = sys.prefix
    sysconfig_platform = sysconfig.get_platform()

    gtk_data = [
        'etc/fonts',
        'etc/gtk-3.0/settings.ini',
        'lib/gdk-pixbuf-2.0',
        'lib/girepository-1.0',
        'share/fontconfig',
        'share/glib-2.0',
        'share/gtksourceview-3.0',
        'share/icons',
    ]
    gtk_exec = []

    if 'mingw' in sysconfig_platform:
        # dll imported by dll dependencies expected to be auto-resolved later
        gtk_exec = [
            'libgtksourceview-3.0-1.dll',
        ]

        # gspawn-helper is needed for Gtk.show_uri function
        if platform.architecture()[0] == '32bit':
            gtk_exec.append('gspawn-win32-helper.exe')
        else:
            gtk_exec.append('gspawn-win64-helper.exe')
        gtk_exec_prefix = os.path.join(gtk_exec_prefix, "bin")
    elif 'win32' in sysconfig_platform or 'win-amd64' in sysconfig_platform:
        # Official python on windows (non-mingw)
        # The required gtk version isn't available,
        # so kept mostly for temporarily keep appveyour build green.
        gtk_exec = [
            'libgtk-3-0.dll',
        ]
        gtk_prefix = os.path.join(gtk_prefix, "Lib", "site-packages", "gnome")
        gtk_exec_prefix = gtk_prefix

    path_list = [(os.path.join(gtk_prefix, path), path) for path in gtk_data]
    path_list += [
        (os.path.join(gtk_exec_prefix, path), path) for path in gtk_exec
    ]
    return path_list


build_exe_options = {
    "includes": ["gi"],
    "excludes": ["tkinter"],
    "packages": ["gi", "weakref"],
    "include_files": get_non_python_dependencies(),
    "zip_exclude_packages": [],
    "zip_include_packages": ["*"],
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

executable_options = {
    "script": "bin/meld",
    "icon": "data/icons/org.gnome.meld.ico",
}

if 'mingw' in sysconfig.get_platform():
    executable_options.update({
         "base": "Win32GUI",  # comment to build cosole version to see stderr
         "targetName": "Meld.exe",
         "shortcutName": "Meld",
         "shortcutDir": "ProgramMenuFolder",
    })

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
    options={
        "build_exe": build_exe_options,
        "bdist_msi": bdist_msi_options,
    },
    executables=[
        Executable(**executable_options),
    ],
    packages=[
        'meld',
        'meld.matchers',
        'meld.ui',
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
    }
)
