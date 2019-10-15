# Install CSS file
install_data(
    [
        files('meld.css')
    ],
    install_dir: join_paths(pkgdatadir)
)

gnome.compile_resources(
  application_id,
  meson.project_name() + '.gresource.xml',
  gresource_bundle: true,
  source_dir: meson.current_build_dir(),
  install_dir: pkgdatadir,
  install: true,
)
