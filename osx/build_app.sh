#!/bin/sh

APP="$PWD/dist/Meld.app"
MAIN="$APP/"
RES="$MAIN/Contents/Resources/"
FRAMEWORKS="$MAIN/Contents/Frameworks/"
INSTROOT="$HOME/gtk/inst/"

glib-compile-schemas data
python setup_py2app.py build
python setup_py2app.py py2app

mkdir -p $RES/share/icons
cp -R $INSTROOT/share/icons/Adwaita $RES/share/icons
cp -R data/icons/* $RES/share/icons

# glib schemas
cp -R $INSTROOT/share/glib-2.0/schemas $RES/share/glib-2.0
cp -R $INSTROOT/share/GConf/gsettings $RES/share/GConf

mkdir -p $RES/etc/pango
pango-querymodules |perl -i -pe 's/^[^#].*\///' > $RES/etc/pango/pango.modules
echo "[Pango]\nModuleFiles=./etc/pango/pango.modules\n" > $RES/etc/pango/pangorc

# gdk-pixbuf
cp -R $INSTROOT/lib/gdk-pixbuf-2.0 $RES/lib
gdk-pixbuf-query-loaders |perl -i -pe 's/^[^#].*\/(lib\/.*")$/"..\/Resources\/$1/' > $RES/lib/gdk-pixbuf-2.0/2.10.0/loaders.cache

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

cp -R data/styles/meld-dark.xml $RES/share/gtksourceview-3.0/styles
cp -R data/styles/meld-base.xml $RES/share/gtksourceview-3.0/styles

# Meld installs in other places than Adwaita - fix it..
cp -R $RES/share/icons/hicolor/* $RES/share/icons/Adwaita

# Update icon cache
pushd .
cd $RES/share/icons/Adwaita
gtk-update-icon-cache -f .
popd

mkdir -p $RES/lib
cp -R $INSTROOT/lib/gtk-3.0 $RES/lib
cp -R $INSTROOT/lib/girepository-1.0 $RES/lib
cp -R $INSTROOT/lib/gobject-introspection $RES/lib

# Some libraries that py2app misses
mkdir -p $FRAMEWORKS
cp -R $INSTROOT/lib/libglib-2.0.0.dylib $FRAMEWORKS
cp -R $INSTROOT/lib/libcairo-gobject.2.dylib $FRAMEWORKS
cp -R $INSTROOT/lib/libcairo-script-interpreter.2.dylib $FRAMEWORKS
cp -R $INSTROOT/lib/libcairo.2.dylib $FRAMEWORKS
cp -R $INSTROOT/lib/libpangocairo-1.0.0.dylib $FRAMEWORKS
cp -R $INSTROOT/lib/libatk-1.0.0.dylib $FRAMEWORKS
cp -R $INSTROOT/lib/libgio-2.0.0.dylib $FRAMEWORKS
cp -R $INSTROOT/lib/libgobject-2.0.0.dylib $FRAMEWORKS
cp -R $INSTROOT/lib/libpango-1.0.0.dylib $FRAMEWORKS
cp -R $INSTROOT/lib/libpangoft2-1.0.0.dylib $FRAMEWORKS
cp -R $INSTROOT/lib/libgtk-3.0.dylib $FRAMEWORKS
cp -R $INSTROOT/lib/libgtksourceview-3.0.1.dylib $FRAMEWORKS
cp -R $INSTROOT/lib/libgtkmacintegration-gtk3.2.dylib $FRAMEWORKS

mv $MAIN/Contents/MacOS/Meld $MAIN/Contents/MacOS/Meld-bin
cp -R osx/Meld $MAIN/Contents/MacOS
chmod +x $MAIN/Contents/MacOS/Meld

pushd .
cd $MAIN/Contents/
# Original from
# https://github.com/apocalyptech/eschalon_utils/blob/master/make-osx-apps.sh
#
# Modify library paths in the modules manually with install_name_tool
# Modified from tegaki create_app_bundle.sh
# Keep looping as long as we added more libraries
newlibs=1
while [ $newlibs -gt 0 ]; do
  newlibs=0
  for dylib in $(find . -name "*.so" -o -name "*.dylib"); do
    echo "Modifying library references in $dylib"
    changes=""
    for lib in `otool -L $dylib | egrep "($INSTROOT|libs/)" | awk '{print $1}'` ; do
      base=`basename $lib`
      changes="$changes -change $lib @executable_path/../Frameworks/$base"
      # Copy the library in if necessary
      if [ ! -f "$FRAMEWORKS/$base" ]; then
        echo "Copying in $lib"
        cp $lib $FRAMEWORKS
        # Loop again so we can pick up this library's dependencies
        newlibs=1
      fi
    done
    if test "x$changes" != x ; then
      if ! install_name_tool $changes $dylib ; then
        echo "Error for $dylib"
      fi
      install_name_tool -id @executable_path/../$dylib $dylib
    fi
  done
done
popd


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
