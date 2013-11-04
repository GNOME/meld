# Created by Sebastian Heinlein
# Modified by Kai Willadsen

import distutils.cmd
import glob
import os.path


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
