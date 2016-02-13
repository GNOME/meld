#!/bin/sh

APP="dist/Meld.app"
MAIN="$APP/"
RES="$MAIN/Contents/Resources/"
INSTROOT="/tmp/meldroot"

glib-compile-schemas data
python setup_py2app.py build
python setup_py2app.py py2app

mkdir -p $RES/share/icons
cp -R $INSTROOT/share/icons/Adwaita $RES/share/icons
cp -R data/icons/* $RES/share/icons

# glib schemas
cp -R $INSTROOT/share/glib-2.0/schemas $RES/share/glib-2.0
cp -R $INSTROOT/share/GConf/gsettings $RES/share/GConf

# gdk-pixbuf
cp -R $INSTROOT/lib/gdk-pixbuf-2.0 $RES/lib

# DIRTY HACK FOR NOW
pushd .
cd $MAIN/Contents/MacOS
ln -s ../Resources/share .
popd

cp -R data/icons/* $RES/share/icons
mkdir -p $RES/share/themes
cp -R $INSTROOT/share/themes/Default/ $RES/share/themes/Default
cp -R $INSTROOT/share/themes/Mac/ $RES/share/themes/Mac
cp -R $INSTROOT/share/gtksourceview-3.0 $RES/share

# Meld installs in other places than Adwaita - fix it..
cp -R $RES/share/icons/hicolor/* $RES/share/icons/Adwaita

mkdir -p $RES/lib
cp -R $INSTROOT/lib/gtk-3.0 $RES/lib
cp -R $INSTROOT/lib/girepository-1.0 $RES/lib

mv $MAIN/Contents/MacOS/Meld $MAIN/Contents/MacOS/Meld-bin
cp -R osx/Meld $MAIN/Contents/MacOS
chmod +x $MAIN/Contents/MacOS/Meld

# Create the dmg file..
hdiutil create -size 250m -fs HFS+ -volname "Meld Merge" myimg.dmg
hdiutil attach myimg.dmg
DEVS=$(hdiutil attach myimg.dmg | cut -f 1)
DEV=$(echo $DEVS | cut -f 1 -d ' ')
rsync  -avzh  $APP /Volumes/Meld\ Merge/
pushd .
cd /Volumes/Meld\ Merge/
ln -sf /Applications "Drag Meld Here"
popd

# Compress the dmg file..
cp osx/DS_Store /Volumes/Meld\ Merge/.DS_Store
hdiutil detach $DEV
hdiutil convert myimg.dmg -format UDZO -o meldmerge.dmg

# Cleanup
mkdir -p osx/Archives
mv meldmerge.dmg osx/Archives
rm -f myimg.dmg
