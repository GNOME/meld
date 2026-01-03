project(
  'meld',
  version : '3.23.2',
  meson_version : '>= 1.2.0',
  license : 'GPL-2.0-or-later',
  license_files : ['COPYING'],
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
dependency('python3', version : '>= 3.10')
dependency('gtk4', version: '>= 4.12')
dependency('glib-2.0', version: '>= 2.80')
dependency('gtksourceview-5', version: '>= 5.0.0')
dependency('libadwaita-1', version : '>= 1.6')
dependency('pygobject-3.0', version: '>= 3.46')
dependency('py3cairo', version: '>= 1.15.0')

profile = get_option('profile')
name_suffix = (profile == 'Devel' ? ' (Development Snapshot)' : '')

resource_base_id = 'org.gnome.Meld'
application_id_no_profile = 'org.gnome.Meld'
application_id = (profile == 'Devel' ? application_id_no_profile + '.' + profile : application_id_no_profile)

prefix = get_option('prefix')

bindir = get_option('bindir')
datadir = get_option('datadir')
localedir = get_option('localedir')
mandir = get_option('mandir')

icondir = datadir / 'icons'
pkgdatadir = datadir / meson.project_name()

itsdir = meson.current_source_dir() / 'gettext'
podir = meson.current_source_dir() / 'po'

gio_schemasdir = dependency('gio-2.0').get_variable(
  pkgconfig: 'schemasdir',
  pkgconfig_define: ['datadir', datadir],
  default_value: datadir / 'glib-2.0/schemas',
)

install_data('COPYING', install_dir: pkgdatadir)

subdir('bin')
subdir('meld')
subdir('data')
subdir('help')
subdir('po')

gnome.post_install(
  glib_compile_schemas: true,
  gtk_update_icon_cache: true,
  update_desktop_database: true,
)
