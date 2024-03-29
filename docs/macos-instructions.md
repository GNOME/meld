
# macOS Instructions


These instructions are designed to allow 
technically proficient users of macOS operating systems 
to be able to make some use of 
the upstream GNOME Meld project code. 

## Introduction

The Meld project does NOT currently support the 
Apple macOS operating system family. 
Neither Apple Mac computer architecture is supported, 
legacy Intel (x64) processors 
nor the newer Apple Silicon (Arm) CPUs. 

There have been fork projects that have produced builds 
to allow the macOS user base to install and run 
binaries based on the Meld project, 
but unfortunately these have not enjoyed 
the same level of development and maintenance effort 
as the multi-resource upstream team 
under the GNOME umbrella. 

This small work-package is starting a minor branch. 
The hope is to attract interest amongst the macOS community 
around the upstream Meld project. 
If it can draw potential development, 
testing, maintenance and support resources into the 
main GNOME Meld project, then they would be able to work together, 
within the existing project structure. 

The envisioned result is a formally-supported macOS build 
that can be delivered through common package management channels, 
to allow the macOS user community to benefit from 
the great features that have resulted from historic development efforts. 

## Running from source with Brew

The following Terminal command line snippets 
use the Homebrew package manager to set up the prerequisites. 
If you are not familiar with Homebrew 
see https://brew.sh/ for information and for installation instructions. 

These instructions are intended for the default macOS shell which is _zsh_. 
If your device is configured to use an alternative shell such as _fish_ or the legacy _bash_, then please run `zsh` first.

These instructions also presume that you are happy for 
the repository to be cloned into your users home folder. 
If you want a different location then please `cd` to it yourself first. 

```zsh
setopt interactivecomments

# first uninstall any older packaged version
brew uninstall meld

# now install GTK+ v3
brew install gtk+3
# GTK+3 will automatically include dependencies like:
# dbus, libxfixes, libxi, libxtst, at-spi2-core, gdk-pixbuf, 
# gsettings-desktop-schemas, hicolor-icon-theme, libepoxy, 
# fribidi, graphite2, icu4c, harfbuzz and pango

# Add the runtime dependencies for meld
brew install gtksourceview4 pygobject3 cairo pkg-config librsvg
# svg loader was not included when gtk+3 loads depend gdk-pixbuf

# obtain the source from this project
git clone https://gitlab.gnome.org/GNOME/meld.git
cd meld
# and use this specific branch
git checkout macos-run-from-src

path=('/opt/homebrew/bin' $path)
export PATH

# ensure that the Glib Gio Settings can be found
typeset -T XDG_DATA_DIRS xdg_data_dirs :
xdg_data_dirs=("$(brew --prefix)/share" $xdg_data_dirs)
export XDG_DATA_DIRS

bin/meld
```

