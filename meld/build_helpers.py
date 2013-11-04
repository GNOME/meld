# Created by Sebastian Heinlein
# Modified by Kai Willadsen

import distutils
import glob
import os
import os.path
import distutils.command.build


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
