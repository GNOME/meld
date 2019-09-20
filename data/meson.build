
# Install schema file
install_data(
  '@0@.gschema.xml'.format(application_id),
  install_dir: schemadir
)

# Install desktop file
desktop_file = i18n.merge_file(
  input: '@0@.desktop.in'.format(application_id),
  output: '@0@.desktop'.format(application_id),
  po_dir: podir,
  type: 'desktop',
  install: true,
  install_dir: desktopdir,
)

# Validate Desktop file
desktop_file_validate = find_program('desktop-file-validate', required: false)
if desktop_file_validate.found()
  test (
    'Validate desktop file',
    desktop_file_validate,
    args: desktop_file.full_path()
  )
endif

# Install AppData file
appdata_file = i18n.merge_file(
  input: '@0@.appdata.xml.in'.format(application_id),
  output: '@0@.appdata.xml'.format(application_id),
  po_dir: podir,
  install: true,
  install_dir: appdatadir,
)

# Validate AppData file
appstreamcli = find_program('appstream-util', required: false)
if appstreamcli.found()
  test(
    'Validate appdata file',
    appstreamcli,
    args: [
        'validate-relax',
        appdata_file.full_path()
     ]
  )
endif

# Install mimetypes
appdata_file = i18n.merge_file(
  input: join_paths('mime', '@0@.xml.in'.format(application_id)),
  output: '@0@.xml'.format(application_id),
  po_dir: podir,
  data_dirs: itsdir,
  install: true,
  install_dir: mimedatadir,
)

# Install CSS file
install_data(
    [
        files('meld.css')
    ],
    install_dir: join_paths(pkgdatadir)
)

# Install GtkSourceview style files
install_data(
    [
        'styles/meld-base.xml',
        'styles/meld-dark.xml'
    ],
    install_dir: join_paths(pkgdatadir, 'styles')
)

# Install icons
icon_sizes = ['scalable']

foreach i : icon_sizes
  install_data(
    join_paths('icons/hicolor', i , 'apps', application_id + '.svg'),
    install_dir: join_paths(icondir, 'hicolor', i , 'apps'),
    rename: '@0@.svg'.format(application_id)
  )
endforeach

# Install the symbolic icon
install_data(
    join_paths('icons/hicolor/symbolic/apps', application_id + '-symbolic.svg'),
    install_dir: join_paths(icondir, 'hicolor', 'symbolic', 'apps'),
    rename: '@0@-symbolic.svg'.format(application_id)
)
