# Meld for OS X #

This README should help you build Meld for OS X. 

*NOTE:* The latest OSX meld is still broken. You may want to switch to the 1.8 branch. I think I need a couple of nights to get this to work. The good new is: I can run it from within the dev environment. The bad news is: Packaging it is not a walk in the park...


### Preparing JHBuild Environment ###

JHBuild is the build system that we will be using to build Meld. This step should really be done once and further builds should not require updating the build environment unless there has been some updates to the libraries that you'd like to do.

---
<<<<<<< HEAD
#### Preparation ####

To ensure that we don't hit some issue with python not able to determine locales on OSX, let's do the following
```
export LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8
```
=======
>>>>>>> da87c5c4fffb10614d606301de670c7807f1f69b

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
<<<<<<< HEAD
You can exit the shell once you determine that it works properly
=======
>>>>>>> da87c5c4fffb10614d606301de670c7807f1f69b

3. Build python
```
jhbuild build python
```

4. Prepare paths and build the bootstrap
```
<<<<<<< HEAD
alias jhbuild="PATH=~/.local/bin:$PATH jhbuild"
=======
alias jhbuild="PATH=gtk-prefix/bin:$PATH jhbuild"
>>>>>>> da87c5c4fffb10614d606301de670c7807f1f69b
jhbuild bootstrap
```

5. Checkout meld and start the initial phase
```
git clone https://github.com/yousseb/meld.git
cd meld
<<<<<<< HEAD
# if building the 1.8 version, run: git checkout meld-1-8
=======
git checkout meld-1-8
>>>>>>> da87c5c4fffb10614d606301de670c7807f1f69b
cd osx/
ln -sf $PWD/jhbuildrc-custom ~/.jhbuildrc-custom
cd ..
jhbuild
```

<<<<<<< HEAD
6- 1.8 branch only: Fix the gtksourceview issues
=======
6- Fix the gtksourceview issues
>>>>>>> da87c5c4fffb10614d606301de670c7807f1f69b
```
ln -sf ~/gtk/inst/lib/pkgconfig/gtk-mac-integration-gtk2.pc ~/gtk/inst/lib/pkgconfig/gtk-mac-integration.pc
```
```
cp ~/Source/gtk/gtksourceview-2.10.5/tests/test-completion.c  ~/Source/gtk/gtksourceview-2.10.5/tests/test-widget.c
```
Edit: ~/Source/gtk/gtksourceview-2.10.5/gtksourceview/gtksourceview-i18n.c
Comment out: 
```
//if (quartz_application_get_bundle_id () != NULL)
//{
//    locale_dir = g_build_filename (quartz_application_get_resource_path (), "share", "locale", NULL);
//}
//else
```

7. Continue the build
```
jhbuild
```

8. Build extra dependencies
```
jhbuild -m osx/meld.modules build meld-python-deps
<<<<<<< HEAD
jhbuild run easy_install py2app
=======
easy_install py2app
>>>>>>> da87c5c4fffb10614d606301de670c7807f1f69b
```

9. You're now ready to build Meld. 
```
<<<<<<< HEAD
chmod +x osx/build_app.sh
jhbuild run osx/build_app.sh
=======
bash osx/build_app.sh
>>>>>>> da87c5c4fffb10614d606301de670c7807f1f69b
```
