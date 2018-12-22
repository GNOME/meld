# Install desktop file
desktop_file = i18n.merge_file(
  input: '@0@.desktop.in'.format(application_id),
  output: '@0@.desktop'.format(application_id),
  po_dir: join_paths(meson.source_root(), 'po'),
  type: 'desktop',
  install: true,
  install_dir: join_paths(get_option('datadir'), 'applications')
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
  po_dir: join_paths(meson.source_root(), 'po'),
  install: true,
  install_dir: join_paths(get_option('datadir'), 'appdata')
)
# Validate AppData file
appstreamcli = find_program('appstream-util', required: false)
if appstreamcli.found()
  test (
    'Validate appdata file',
    appstreamcli,
    args: [
        'validate-relax',
        appdata_file.full_path()
     ]
  )
endif
# Install Schehma file
install_data(
  '@0@.gschema.xml'.format(application_id),
  install_dir : join_paths(get_option('datadir'), 'glib-2.0', 'schemas')
)
# Install CSS file
install_data(
    [
        files('meld.css')
    ],
    install_dir: join_paths(get_option('datadir'), meson.project_name())
)
# Install the UI files
install_data(
    [
        'ui/application.ui',
        'ui/appmenu-fallback.xml',
        'ui/dirdiff-ui.xml',
        'ui/dirdiff.ui',
        'ui/EditableList.ui',
        'ui/encoding-selector.ui',
        'ui/filediff-ui.xml',
        'ui/filediff.ui',
        'ui/findbar.ui',
        'ui/language-selector.ui',
        'ui/meldapp-ui.xml',
        'ui/meldapp.ui',
        'ui/patch-dialog.ui',
        'ui/preferences.ui',
        'ui/shortcuts.ui',
        'ui/tab-placeholder.ui',
        'ui/vcview-ui.xml',
        'ui/vcview.ui'
    ],
    install_dir: join_paths(get_option('datadir'), meson.project_name(), 'ui')
)
# Install the styles files
install_data(
    [
        'styles/meld-base.xml',
        'styles/meld-dark.xml'
    ],
    install_dir: join_paths(get_option('datadir'), meson.project_name(), 'styles')
)
# Install the mimetypes
appdata_file = i18n.merge_file(
  input: join_paths('mime', '@0@.xml.in'.format(application_id)),
  output: '@0@.xml'.format(application_id),
  po_dir: join_paths(meson.source_root(), 'po'),
  install: true,
  install_dir: join_paths(get_option('datadir'), 'mime', 'packages')
)
subdir('icons')