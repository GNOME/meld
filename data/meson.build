# Install man page
install_man('meld.1')

# Install schema file
install_data(
  '@0@.gschema.xml'.format(resource_base_id),
  install_dir: gio_schemasdir,
)

# Install desktop file
desktop_file = i18n.merge_file(
  input: configure_file(
    input: '@0@.desktop.in.in'.format(resource_base_id),
    output: '@0@.desktop.in'.format(application_id),
    configuration: {'icon': application_id},
  ),
  output: '@0@.desktop'.format(application_id),
  po_dir: podir,
  type: 'desktop',
  install: true,
  install_dir: datadir / 'applications',
)

# Validate Desktop file
desktop_file_validate = find_program('desktop-file-validate', required: false)
if desktop_file_validate.found()
  test (
    'Validate desktop file',
    desktop_file_validate,
    args: desktop_file.full_path(),
  )
endif

appdata_file = i18n.merge_file(
  input: configure_file(
    input: files('org.gnome.Meld.appdata.xml.in.in'),
    output: 'org.gnome.Meld.appdata.xml.in',
    configuration: {'appid': application_id},
  ),
  output: '@0@.appdata.xml'.format(application_id),
  po_dir: podir,
  install: true,
  install_dir: datadir / 'metainfo',
)

# Validate AppData file
appstreamcli = find_program('appstreamcli', required: false)
if appstreamcli.found()
  test(
    'Validate appdata file',
    appstreamcli,
    args: ['validate', '--no-net', '--explain', appdata_file.full_path()],
  )
endif

# Install mimetypes
mimetype_file = i18n.merge_file(
  input: 'mime' / '@0@.xml.in'.format(resource_base_id),
  output: '@0@.xml'.format(application_id),
  po_dir: podir,
  data_dirs: itsdir,
  install: true,
  install_dir: datadir / 'mime/packages',
)

# Check GSettings schema
compile_schemas = find_program('glib-compile-schemas', required: false)
if compile_schemas.found()
  test(
    'Validate schema file',
    compile_schemas,
    args: ['--strict', '--dry-run', meson.current_source_dir()],
  )
endif

# Install GtkSourceview style files
styles = [
  'meld-base.style-scheme.xml',
  'meld-dark.style-scheme.xml',
]

foreach style: styles
  i18n.merge_file(
    input: 'styles' / style + '.in',
    output: style,
    po_dir: podir,
    data_dirs: itsdir,
    install: true,
    install_dir: pkgdatadir / 'styles',
  )
endforeach

# Install icons
icon_sizes = ['scalable']

foreach i: icon_sizes
  install_data(
    'icons/hicolor' / i / 'apps' / application_id + '.svg',
    install_dir: icondir / 'hicolor' / i / 'apps',
    rename: '@0@.svg'.format(application_id),
  )
endforeach

# Install the symbolic icon
install_data(
  'icons/hicolor/symbolic/apps' / application_id_no_profile + '-symbolic.svg',
  install_dir: icondir / 'hicolor/symbolic/apps',
  rename: '@0@-symbolic.svg'.format(application_id),
)
