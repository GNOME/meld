metainfo_file = i18n.merge_file(
  input: configure_file(
    input: files('org.gnome.Meld.metainfo.xml.in.in'),
    output: 'org.gnome.Meld.metainfo.xml.in',
    configuration: {'appid': application_id_no_profile},
  ),
  output: '@0@.metainfo.xml'.format(application_id_no_profile),
  po_dir: podir,
  install: true,
  install_dir: datadir / 'metainfo',
)

# Validate metainfo file
appstreamcli = find_program('appstreamcli', required: false)
if appstreamcli.found()
  test(
    'Validate metainfo file',
    appstreamcli,
    args: ['validate', '--no-net', '--explain', metainfo_file.full_path()],
  )
endif
