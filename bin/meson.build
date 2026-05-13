
configure_file(
    input: 'meld',
    output: 'meld',
    command: ['../meson_shebang_normalisation.py', '@INPUT@', '@OUTPUT@'] + (is_wheel ? ['--wheel'] : []),
    install_dir: bindir,
)
