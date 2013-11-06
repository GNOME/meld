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


class build_i18n(distutils.cmd.Command):

    description = "integrate the gettext framework"

    user_options = [('desktop-files=', None, '.desktop.in files that '
                                             'should be merged'),
                    ('xml-files=', None, '.xml.in files that should be '
                                         'merged'),
                    ('schemas-files=', None, '.schemas.in files that '
                                             'should be merged'),
                    ('ba-files=', None, 'bonobo-activation files that '
                                        'should be merged'),
                    ('rfc822deb-files=', None, 'RFC822 files that should '
                                               'be merged'),
                    ('key-files=', None, '.key.in files that should be '
                                         'merged'),
                    ('domain=', 'd', 'gettext domain'),
                    ('merge-po', 'm', 'merge po files against template'),
                    ('po-dir=', 'p', 'directory that holds the i18n files'),
                    ('bug-contact=', None, 'contact address for msgid bugs')]

    boolean_options = ['merge-po']

    def initialize_options(self):
        self.desktop_files = []
        self.xml_files = []
        self.key_files = []
        self.schemas_files = []
        self.ba_files = []
        self.rfc822deb_files = []
        self.domain = None
        self.merge_po = False
        self.bug_contact = None
        self.po_dir = None

    def finalize_options(self):
        if self.domain is None:
            self.domain = self.distribution.metadata.name
        if self.po_dir is None:
            self.po_dir = "po"

    def run(self):
        """
        Update the language files, generate mo files and add them
        to the to be installed files
        """
        if not os.path.isdir(self.po_dir):
            return

        data_files = self.distribution.data_files
        if data_files is None:
            # in case not data_files are defined in setup.py
            self.distribution.data_files = data_files = []

        if self.bug_contact is not None:
            os.environ["XGETTEXT_ARGS"] = "--msgid-bugs-address=%s " % \
                                          self.bug_contact

        # Print a warning if there is a Makefile that would overwrite our
        # values
        if os.path.exists("%s/Makefile" % self.po_dir):
            self.announce("""
WARNING: Intltool will use the values specified from the
         existing po/Makefile in favor of the vaules
         from setup.cfg.
         Remove the Makefile to avoid problems.""")

        # If there is a po/LINGUAS file, or the LINGUAS environment variable
        # is set, only compile the languages listed there.
        selected_languages = None
        linguas_file = os.path.join(self.po_dir, "LINGUAS")
        if os.path.isfile(linguas_file):
            selected_languages = open(linguas_file).read().split()
        if "LINGUAS" in os.environ:
            selected_languages = os.environ["LINGUAS"].split()

        # Update po(t) files and print a report
        # We have to change the working dir to the po dir for intltool
        cmd = ["intltool-update", (self.merge_po and "-r" or "-p"), "-g", self.domain]
        wd = os.getcwd()
        os.chdir(self.po_dir)
        self.spawn(cmd)
        os.chdir(wd)
        max_po_mtime = 0
        for po_file in glob.glob("%s/*.po" % self.po_dir):
            lang = os.path.basename(po_file[:-3])
            if selected_languages and not lang in selected_languages:
                continue
            mo_dir =  os.path.join("build", "mo", lang, "LC_MESSAGES")
            mo_file = os.path.join(mo_dir, "%s.mo" % self.domain)
            if not os.path.exists(mo_dir):
                os.makedirs(mo_dir)
            cmd = ["msgfmt", po_file, "-o", mo_file]
            po_mtime = os.path.getmtime(po_file)
            mo_mtime = os.path.exists(mo_file) and os.path.getmtime(mo_file) or 0
            if po_mtime > max_po_mtime:
                max_po_mtime = po_mtime
            if po_mtime > mo_mtime:
                self.spawn(cmd)

            targetpath = os.path.join("share/locale", lang, "LC_MESSAGES")
            data_files.append((targetpath, (mo_file,)))

        # merge .in with translation
        for (option, switch) in ((self.xml_files, "-x"),
                                 (self.desktop_files, "-d"),
                                 (self.schemas_files, "-s"),
                                 (self.rfc822deb_files, "-r"),
                                 (self.ba_files, "-b"),
                                 (self.key_files, "-k"),):
            try:
                file_set = eval(option)
            except:
                continue
            for (target, files) in file_set:
                build_target = os.path.join("build", target)
                if not os.path.exists(build_target): 
                    os.makedirs(build_target)
                files_merged = []
                for file in files:
                    if file.endswith(".in"):
                        file_merged = os.path.basename(file[:-3])
                    else:
                        file_merged = os.path.basename(file)
                    file_merged = os.path.join(build_target, file_merged)
                    cmd = ["intltool-merge", switch, self.po_dir, file, 
                           file_merged]
                    mtime_merged = os.path.exists(file_merged) and \
                                   os.path.getmtime(file_merged) or 0
                    mtime_file = os.path.getmtime(file)
                    if mtime_merged < max_po_mtime or mtime_merged < mtime_file:
                        # Only build if output is older than input (.po,.in) 
                        self.spawn(cmd)
                    files_merged.append(file_merged)
                data_files.append((target, files_merged))
