project(
    'meld',
    version: '3.21.0',
    meson_version: '>=0.49.0',
)

python = import('python')
i18n = import('i18n')
gnome = import('gnome')

python3 = python.find_installation('python3')
if not python3.found()
    error('Python 3 is required to build and use Meld')
endif

# These requirements are kept in both `bin/meld` and `meson.build`. If you
# update one, update the other.
dependency('python3', version : '>= 3.6')
dependency('gtk+-3.0', version: '>= 3.20')
dependency('glib-2.0', version: '>= 2.48')
dependency('gtksourceview-4', version: '>= 4.0.0')
dependency('pygobject-3.0', version: '>= 3.30')
dependency('py3cairo', version: '>= 1.15.0')


profile = get_option('profile')
name_suffix = (profile == 'Devel' ? ' (Development Snapshot)' : '')

resource_base_id = 'org.gnome.meld'
application_id_no_profile = 'org.gnome.Meld'
application_id = 'org.gnome.Meld@0@'.format(profile)

prefix = get_option('prefix')

bindir = prefix / get_option('bindir')
datadir = prefix / get_option('datadir')
libexecdir = prefix / get_option('libexecdir')
localedir = prefix / get_option('localedir')
mandir = prefix / get_option('mandir')

appdatadir = datadir / 'metainfo'
desktopdir = datadir / 'applications'
icondir = datadir / 'icons'
mimedatadir = datadir / 'mime/packages'
pkgdatadir = datadir / meson.project_name()
schemadir = datadir / 'glib-2.0/schemas'

itsdir = meson.current_source_dir() / 'gettext'
podir = meson.current_source_dir() / 'po'

subdir('meld')
subdir('data')
subdir('help')
subdir('po')

install_data('bin/meld', install_dir: bindir)

if get_option('byte-compile')
    meson.add_install_script('meson_post_install.py', python3.get_install_dir())
else
    meson.add_install_script('meson_post_install.py')
endif
