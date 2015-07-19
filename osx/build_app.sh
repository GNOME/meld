#!/bin/sh

#jhbuild bootstrap ; jhbuild; jhbuild build gtk-mac-integration; jhbuild
#jhbuild -m osx/meld.modules build meld-python-deps
#jhbuild shell
#easy_install pip
#pip install pygtksourceview

<<<<<<< HEAD
jhbuild run python setup_py2app.py build
jhbuild run python setup_py2app.py py2app
=======

python setup_py2app.py build
python setup_py2app.py py2app
>>>>>>> da87c5c4fffb10614d606301de670c7807f1f69b

APP="dist/Meld.app"
MAIN="$APP/"
RES="$MAIN/Contents/Resources/"

mkdir -p $RES/share/icons
cp -R ~/gtk/inst/share/icons/Tango $RES/share/icons
<<<<<<< HEAD
mv $RES/share/icons/Tango $RES/share/icons/Adwaita
cp -R data/icons/* $RES/share/icons

# glib schemas
cp -R ~/gtk/inst/share/glib-2.0/schemas $RES/share/glib-2.0
cp -R ~/gtk/inst/share/GConf/gsettings $RES/share/GConf

# DIRTY HACK FOR NOW
pushd .
cd $MAIN/Contents/MacOS
ln -s ../Resources/share .
popd

=======
#cp -R ~/gtk/inst/share/icons/hicolor $RES/share/icons
cp -R data/icons/* $RES/share/icons

>>>>>>> da87c5c4fffb10614d606301de670c7807f1f69b
mkdir -p $RES/share/themes
cp -R ~/gtk/inst/share/themes/Clearlooks/ $RES/share/themes/Clearlooks
cp -R ~/gtk/inst/share/themes/Mac/ $RES/share/themes/Mac

<<<<<<< HEAD
cp -R ~/gtk/inst/share/gtksourceview-3.0 $RES/share

mkdir -p $RES/etc/gtk-3.0
#mkdir -p $RES/etc/pango
#mkdir -p $RES/etc/xdg
cp -R osx/gtkrc $RES/etc/gtk-3.0
=======
cp -R ~/gtk/inst/share/gtksourceview-2.0 $RES/share

mkdir -p $RES/etc/gtk-2.0
mkdir -p $RES/etc/pango
mkdir -p $RES/etc/xdg
cp -R osx/gtkrc $RES/etc/gtk-2.0
>>>>>>> da87c5c4fffb10614d606301de670c7807f1f69b
cp -R osx/pangorc $RES/etc/pango

mkdir -p $RES/lib

<<<<<<< HEAD
#cp -R ~/gtk/inst/lib/girepository-1.0 $RES/lib
cp -R ~/gtk/inst/lib/gtk-3.0 $RES/lib
=======
cp -R ~/gtk/inst/lib/girepository-1.0 $RES/lib
cp -R ~/gtk/inst/lib/gtk-2.0 $RES/lib
>>>>>>> da87c5c4fffb10614d606301de670c7807f1f69b

mv $MAIN/Contents/MacOS/Meld $MAIN/Contents/MacOS/Meld-bin
cp -R osx/Meld $MAIN/Contents/MacOS
chmod +x $MAIN/Contents/MacOS/Meld
#cp -R ~/gtk/inst/lib/pango $RES/lib

hdiutil create -size 250m -fs HFS+ -volname "Meld Merge" myimg.dmg
hdiutil attach myimg.dmg
DEVS=$(hdiutil attach myimg.dmg | cut -f 1)
DEV=$(echo $DEVS | cut -f 1 -d ' ')
rsync  -avzh  $APP /Volumes/Meld\ Merge/
pushd .
cd /Volumes/Meld\ Merge/
ln -sf /Applications "Drag Meld Here"
popd
cp osx/DS_Store /Volumes/Meld\ Merge/.DS_Store
hdiutil detach $DEV
hdiutil convert myimg.dmg -format UDZO -o meldmerge.dmg





#http://mirror.pnl.gov/macports/release/ports/net/deluge/files/patch-remove-osx-native-menus.diff
#and gtk.gdk.WINDOWING == "quartz":
