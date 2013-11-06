# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.

# Copied and adapted from the DistUtilsExtra project
# Created by Sebastian Heinlein and Martin Pitt
# Copyright Canonical Ltd.

# Modified by Kai Willadsen for the Meld project
# Copyright (C) 2013 Kai Willadsen <kai.willadsen@gmail.com>


import distutils.cmd
import distutils.command.build
import glob
import os.path


class build_extra(distutils.command.build.build):

    def __init__(self, dist):
        distutils.command.build.build.__init__(self, dist)

        def has_help(command):
            return "build_help" in self.distribution.cmdclass

        def has_icons(command):
            return "build_icons" in self.distribution.cmdclass

        def has_i18n(command):
            return "build_i18n" in self.distribution.cmdclass

        self.sub_commands.append(("build_i18n", has_i18n))
        self.sub_commands.append(("build_icons", has_icons))
        self.sub_commands.append(("build_help", has_help))


class build_help(distutils.cmd.Command):

    help_dir = 'help'

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def get_data_files(self):
        data_files = []
        name = self.distribution.metadata.name

        for path in glob.glob(os.path.join(self.help_dir, '*')):
            lang = os.path.basename(path)
            path_help = os.path.join('share/help', lang, name)
            path_figures = os.path.join('share/help', lang, name, 'figures')
            
            xml_files = glob.glob('%s/*.xml' % path)
            mallard_files = glob.glob('%s/*.page' % path)
            data_files.append((path_help, xml_files + mallard_files))
            data_files.append((path_figures, glob.glob('%s/figures/*.png' % path)))

        return data_files
    
    def run(self):
        data_files = self.distribution.data_files
        data_files.extend(self.get_data_files())


class build_icons(distutils.cmd.Command):

    icon_dir = os.path.join("data","icons")

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        data_files = self.distribution.data_files

        for theme in glob.glob(os.path.join(self.icon_dir, "*")):
            for size in glob.glob(os.path.join(theme, "*")):
                for category in glob.glob(os.path.join(size, "*")):
                    icons = []
                    for icon in glob.glob(os.path.join(category,"*")):
                        if not os.path.islink(icon):
                            icons.append(icon)
                    if not icons:
                        continue
                    data_files.append(("share/icons/%s/%s/%s" %
                                       (os.path.basename(theme),
                                        os.path.basename(size),
                                        os.path.basename(category)),
                                        icons))
