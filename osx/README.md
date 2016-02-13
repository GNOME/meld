Meld for OS X
===========

This README should help you build Meld for OS X.

### Preparing JHBuild Environment ###

JHBuild is the build system that we will be using to build Meld. This step should really be done once and further builds should not require updating the build environment unless there has been some updates to the libraries that you'd like to do.

---
#### Preparation ####

To ensure that we don't hit some issue with python not able to determine locales on OSX, let's do the following
```
export LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8
```

#### Initial Phase ####

 1. Download the setup script
	```
	cd ~
	curl -O https://git.gnome.org/browse/gtk-osx/plain/gtk-osx-build-setup.sh
	```

 2. Run the setup script
	```
	sh gtk-osx-build-setup.sh
	~/.local/bin/jhbuild shell
	```
	You can exit the shell once you determine that it works properly

 3. Prepare paths and build the bootstrap
	```
  export PATH="~/.local/bin/:$PATH"
	jhbuild bootstrap
	```

 4. Checkout meld and start the initial phase
	```
	git clone https://github.com/yousseb/meld.git
	cd meld
	cd osx/
	ln -sf $PWD/jhbuildrc-custom ~/.jhbuildrc-custom
	cd ..
	```

#### Building Meld ####

 1. Build python - with libxml2 support
	```
	jhbuild -m osx/meld.modules build python-withxml2
	```

 2. Build the rest of meld dependencies
	```
	jhbuild  -m osx/meld.modules build meld-deps
	```

 3. You're now ready to build Meld.
	```
	chmod +x osx/build_app.sh
	jhbuild run osx/build_app.sh
	```
	or
	```
	jhbuild shell
	chmod +x osx/build_app.sh
	./osx/build_app.sh
	```

#### Output ####

> **DMG:** Find the DMG <i class="icon-folder-open"></i> file  in osx/Archives after you're done building.

#### FQA ####
1. Can't run jhbuild bootstrap - gives an error related to bash
  Issue the following command:
	```
	mkdir -p $HOME/gtk/inst/bin
	ln -sf /bin/bash $HOME/gtk/inst/bin/bash
	```

2. Build stops at Adwaita theme
  So you see lots of the following error?
  ```
  Can't load file: Unrecognized image file format
  ```
  1. Select the option to **Start shell**.
  2. Issue the commands:
    ```
    mv /tmp/meldroot/bin/gtk-encode-symbolic-svg /tmp/meldroot/bin/gtk-encode-symbolic-svg.orig
    ./configure
    ```
  3. Exit the shell: type ``` exit ```
  4. Choose **Rerun phase install**.
  We won't have SVG icons... Sucks but better than not having meld. If someone can help, please do.
