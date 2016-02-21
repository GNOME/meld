Meld for OS X
===========

This README should help you build Meld for OS X.

> :bulb:**Tip:** A lot of people are asking how to use this package as a git difftool.
> Once installed, edit your ```~/.gitconfig```, and add the following lines
> ```
	[diff]
		tool = meld
	[difftool]
		prompt = false
	[difftool "meld"]
		trustExitCode = true
		cmd = /Applications/Meld.app/Contents/MacOS/Meld \"$LOCAL\" \"$PWD/$REMOTE\"
  ```

### Preparing JHBuild Environment ###

JHBuild is the build system that we will be using to build Meld. This step should really be done once and further builds should not require updating the build environment unless there have been some updates to the libraries that you'd like to do.

---
#### Preparation ####

To ensure that we don't hit some issue with python not able to determine locales on OSX, let's do the following
```
export LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8
```

> :bulb:**Tip:** Renaming /opt/local (MacPorts) during the initial build of the the build
environment proved to reduce collisions later on. You might want to consider doing this..

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

This can probably be done in the meld.modules file. Unfortunately I don't have
the time to fix the order/dependencies. So let's do it one by one. The following
is the list of the exact steps followed during the build to reduce conflicts

 1. Build python - with libxml2 support
	```
	jhbuild -m osx/meld.modules build python-withxml2
	```

 2. Build graphics dependencies
 	```
 	jhbuild  -m osx/meld.modules build graphics-dependencies
 	```

 3. Build the rest of meld dependencies (rebuilding previous dependencies as well)
	```
	jhbuild  -m osx/meld.modules build meld-deps -f
	```

 4. You're now ready to build Meld.
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

> :bulb:**Output:** Find the output dmg file in osx/Archives after you're done building.

#### FAQ ####

1. Can't run jhbuild bootstrap - gives an error related to bash not being found.
	```
	mkdir -p $HOME/gtk/inst/bin; 
	ln -sf /bin/bash $HOME/gtk/inst/bin/bash
	```
