shebang_command = ['../meson_shebang_normalisation.py', '@INPUT@', '@OUTPUT@']
if is_wheel
  shebang_command += '--wheel'
endif

configure_file(
  input: 'meld',
  output: 'meld',
  command: shebang_command,
  install_dir: bindir,
)
