project(
    'meld',
    version: '3.21.0',
    meson_version: '>=0.47.0',
)

python = import('python')
i18n = import('i18n')
gnome = import('gnome')

python3 = python.find_installation('python3')
if not python3.found()
    error('Python 3 is required to build and use Meld')
endif

dependency('gtk+-3.0', version: '>= 3.20')
dependency('glib-2.0', version: '>= 2.48')
dependency('gtksourceview-4', version: '>= 4.0.0')


if get_option('profile') == 'Devel'
    name_suffix = ' (Development Snapshot)'
    profile = 'Devel'
else
    name_suffix = ''
    profile = ''
endif

resource_base_id = 'org.gnome.meld'
application_id = 'org.gnome.Meld@0@'.format(profile)

prefix = get_option('prefix')

bindir = join_paths(prefix, get_option('bindir'))
datadir = join_paths(prefix, get_option('datadir'))
libexecdir = join_paths(prefix, get_option('libexecdir'))
localedir = join_paths(prefix, get_option('localedir'))
mandir = join_paths(prefix, get_option('mandir'))

appdatadir = join_paths(datadir, 'metainfo')
desktopdir = join_paths(datadir, 'applications')
icondir = join_paths(datadir, 'icons')
mimedatadir = join_paths(datadir, 'mime', 'packages')
pkgdatadir = join_paths(datadir, meson.project_name())
schemadir = join_paths(datadir, 'glib-2.0', 'schemas')

itsdir = join_paths(meson.current_source_dir(), 'gettext')
podir = join_paths(meson.current_source_dir(), 'po')

subdir('meld')
subdir('data')
subdir('help')
subdir('po')

install_data('bin/meld', install_dir: bindir)

meson.add_install_script('meson_post_install.py')
