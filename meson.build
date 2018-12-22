project('meld', version: '3.19.1',
    meson_version: '>=0.46.0')

application_id = 'org.gnome.meld'

python = import('python')
i18n = import('i18n')
gnome = import('gnome')

python3 = python.find_installation('python3')
if not python3.found()
    error('Python 3 is required to build and use Meld')
endif

dependency('gtk+-3.0', version: '>= 3.20')
dependency('glib-2.0', version: '>= 2.48')
dependency('gtksourceview-3.0', version: '>= 3.20.0')



subdir('data')
subdir('help')
subdir('po')


install_data(
    [
        'bin/meld'
    ],
    install_dir: get_option('bindir')
)
install_subdir(
    meson.project_name(),
    install_dir: python3.get_path('purelib')
)

meson.add_install_script('meson_post_install.py')