# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or (at
# your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Copied and adapted from the DistUtilsExtra project
# Created by Sebastian Heinlein and Martin Pitt
# Copyright Canonical Ltd.

# Modified by Kai Willadsen for the Meld project
# Copyright (C) 2013-2014 Kai Willadsen <kai.willadsen@gmail.com>

import distutils.cmd
import distutils.command.build
import distutils.command.build_py
import distutils.command.install
import distutils.command.install_data
import distutils.dir_util
import distutils.dist
import glob
import os.path
import shutil
from distutils.log import info

import cx_Freeze


def has_icons(self):
    return "build_icons" in self.distribution.cmdclass


def has_data(self):
    return "build_data" in self.distribution.cmdclass


cx_Freeze.command.build.Build.sub_commands.extend([
    ("build_icons", has_icons),
    ("build_data", has_data),
])


class build_data(distutils.cmd.Command):

    gschemas = [
        ('share/glib-2.0/schemas', ['data/org.gnome.meld.gschema.xml'])
    ]

    frozen_gschemas = [
        ('share/meld', ['data/gschemas.compiled']),
    ]

    win32_settings_ini = '[Settings]\ngtk-application-prefer-dark-theme=0\n'

    style_source = "data/styles/*.style-scheme.xml.in"
    style_target_dir = 'share/meld/styles'

    mime_source = "data/mime/*.xml.in"
    mime_target_dir = "share/mime/packages"

    # FIXME: This is way too much hard coding, but I really hope
    # it also doesn't last that long.
    resource_source = "meld/resources/meld.gresource.xml"
    resource_target = "org.gnome.Meld.gresource"

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def get_data_files(self):
        data_files = []

        build_path = os.path.join('build', 'data')
        if not os.path.exists(build_path):
            os.makedirs(build_path)

        info("compiling gresources")
        resource_dir = os.path.dirname(self.resource_source)
        target = os.path.join(build_path, self.resource_target)
        self.spawn([
            "glib-compile-resources",
            "--target={}".format(target),
            "--sourcedir={}".format(resource_dir),
            "--sourcedir={}".format("data/icons/hicolor"),
            self.resource_source,
        ])

        data_files.append(('share/meld', [target]))

        # Write out a default settings.ini for Windows to make
        # e.g., dark theme selection slightly easier.
        settings_dir = os.path.join('build', 'etc', 'gtk-3.0')
        if not os.path.exists(settings_dir):
            os.makedirs(settings_dir)
        settings_path = os.path.join(settings_dir, 'settings.ini')
        with open(settings_path, 'w') as f:
            print(self.win32_settings_ini, file=f)

        gschemas = self.frozen_gschemas + [
            ('etc/gtk-3.0', [settings_path])
        ]

        data_files.extend(gschemas)

        # We don't support i18n on Windows, so we just copy these here
        styles = glob.glob(self.style_source)

        targets = []
        for style in styles:
            assert style.endswith('.in')
            target = style[:-len('.in')]
            shutil.copyfile(style, target)
            targets.append(target)

        data_files.append((self.style_target_dir, targets))

        # We don't support i18n on Windows, so we just copy these here
        mime_definitions = glob.glob(self.mime_source)

        targets = []
        for mime in mime_definitions:
            assert mime.endswith('.in')
            target = mime[:-len('.in')]
            shutil.copyfile(mime, target)
            targets.append(target)

        data_files.append((self.mime_target_dir, targets))

        return data_files

    def run(self):
        data_files = self.distribution.data_files
        data_files.extend(self.get_data_files())


class build_icons(distutils.cmd.Command):

    icon_dir = os.path.join("data", "icons")
    target = "share/icons"
    frozen_target = "share/meld/icons"

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        target_dir = self.frozen_target
        data_files = self.distribution.data_files

        for theme in glob.glob(os.path.join(self.icon_dir, "*")):
            for size in glob.glob(os.path.join(theme, "*")):
                for category in glob.glob(os.path.join(size, "*")):
                    icons = (glob.glob(os.path.join(category, "*.png")) +
                             glob.glob(os.path.join(category, "*.svg")))
                    icons = [
                        icon for icon in icons if not os.path.islink(icon)]
                    if not icons:
                        continue
                    data_files.append(("%s/%s/%s/%s" %
                                       (target_dir,
                                        os.path.basename(theme),
                                        os.path.basename(size),
                                        os.path.basename(category)),
                                       icons))
