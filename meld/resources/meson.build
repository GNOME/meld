subdir('data')

gnome.compile_resources(
  application_id,
  meson.project_name() + '.gresource.xml',
  gresource_bundle: true,
  dependencies: metainfo_file,
  source_dir: [
    meson.current_build_dir(),
    meson.project_source_root() / 'data' / 'icons' / 'hicolor',
  ],
  install_dir: pkgdatadir,
  install: true,
)
