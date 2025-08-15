
# TODO: Replace our existing conf.py hacks with configure_file().
# See e.g., gnome-music for an example of this

folders = {
  '.': [
    '__init__.py',
    'accelerators.py',
    'actiongutter.py',
    'chunkmap.py',
    'const.py',
    'diffgrid.py',
    'dirdiff.py',
    'externalhelpers.py',
    'filediff.py',
    'filters.py',
    'gutterrendererchunk.py',
    'imagediff.py',
    'iohelpers.py',
    'linkmap.py',
    'meldapp.py',
    'meldbuffer.py',
    'melddoc.py',
    'meldwindow.py',
    'menuhelpers.py',
    'misc.py',
    'newdifftab.py',
    'patchdialog.py',
    'preferences.py',
    'recent.py',
    'settings.py',
    'sourceview.py',
    'style.py',
    'task.py',
    'tree.py',
    'treehelpers.py',
    'undo.py',
    'vcview.py',
    'windowstate.py',
  ],
  'matchers': [
    'matchers/__init__.py',
    'matchers/diffutil.py',
    'matchers/helpers.py',
    'matchers/merge.py',
    'matchers/myers.py',
  ],
  'ui': [
    'ui/__init__.py',
    'ui/bufferselectors.py',
    'ui/cellrenderers.py',
    'ui/emblemcellrenderer.py',
    'ui/filebutton.py',
    'ui/findbar.py',
    'ui/gladesupport.py',
    'ui/gtkcompat.py',
    'ui/gtkutil.py',
    'ui/historyentry.py',
    'ui/listwidget.py',
    'ui/msgarea.py',
    'ui/notebook.py',
    'ui/notebooklabel.py',
    'ui/pathlabel.py',
    'ui/recentselector.py',
    'ui/statusbar.py',
    'ui/util.py',
    'ui/vcdialogs.py',
  ],
  'vc': [
    'vc/COPYING',
    'vc/README',
    'vc/__init__.py',
    'vc/_null.py',
    'vc/_vc.py',
    'vc/bzr.py',
    'vc/cvs.py',
    'vc/darcs.py',
    'vc/git.py',
    'vc/mercurial.py',
    'vc/svn.py',
  ],
}

foreach folder_name, sources: folders
  pkgdir = meson.project_name() / folder_name
  python3.install_sources(sources, pure: true, subdir: pkgdir)
endforeach

# Install the executable file
app_config = {
  'profile': profile,
  'application_id': application_id,
  'resource_base_id': resource_base_id,
  'localedir': prefix / localedir,
  'pkgdatadir': prefix / pkgdatadir,
  'configured': 'True',
}

configure_file(
  input: 'conf.py.in',
  output: 'conf.py',
  configuration: app_config,
  install_dir: python3.get_install_dir(pure: true, subdir: meson.project_name()),
)

subdir('resources')
