#!/bin/sh
rm -rf darcstest*

mkdir darcstest1
cd darcstest1
darcs init
echo "normal" > normal.txt
echo "renamed" > renamed.txt
echo "modified" > modified.txt
echo "deleted" > deleted.txt
echo "conflict" > conflict.txt
echo "conflict2" > conflict2.txt

mkdir normal-dir
mkdir renamed-dir
echo "subfile" > ./renamed-dir/subfile
mkdir modified-dir
mkdir deleted-dir

darcs add * -r
darcs record -a -m "First patch"

# create conflict

cd ..
darcs clone darcstest1 darcstest2

cd darcstest1
echo "parent change" >> conflict.txt
echo "parent change" >> conflict2.txt
darcs record -a -m "Parent change"

cd ../darcstest2
echo "child change" >> conflict.txt
echo "child change" >> conflict2.txt
darcs record -a -m "Child change"
darcs pull -a

# conflicts
# they are currently not reported by darcs whatsnew
# see http://bugs.darcs.net/issue2138

# Add new file
# Add new directory
echo "new" > new.txt
mkdir new-dir
echo "new-dir-file" > ./new-dir/new-dir-file.txt
darcs add ./new.txt
darcs add ./new-dir

# Delete a file
# delete a directory
darcs remove deleted.txt
# Meld doesn't track this unless there's files below it....
darcs remove deleted-dir

# Rename a file
# Rename a directory
darcs move renamed.txt renamed-new.txt
# darcs shows the directory as renamed, but not any subfiles. (different to git)
# Meld will not show the directory rename unless there are subfiles.
darcs move renamed-dir renamed-new-dir

# Modify a file
echo "modified" >> modified.txt
# Modify a directory.... how?

darcs move ./conflict2.txt ./conflict2-moved.txt
