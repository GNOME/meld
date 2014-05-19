#!/bin/sh
rm -R bzrtest*

mkdir bzrtest1
cd bzrtest1
bzr init
echo "normal" > normal.txt
echo "renamed" > renamed.txt
echo "modified" > modified.txt
echo "deleted" > deleted.txt
echo "exec" > exec.txt
echo "conflict" > conflict.txt
echo "conflict2" > conflict2.txt

mkdir normal-dir
mkdir renamed-dir
echo "subfile" > ./renamed-dir/subfile
mkdir modified-dir
mkdir deleted-dir
mkdir exec-dir

bzr add *
bzr commit -m "Initial commit"


# CHDIR and do a merge
cd ..
bzr branch bzrtest1 bzrtest2

# Make a change back in the original branch so we get a conflict
cd bzrtest1
echo "parent change" >> conflict.txt
echo "parent change" >> conflict2.txt
bzr commit -m "Parent change"

# CD back to the new branch and make a change
cd ../bzrtest2
echo "child change" >> conflict.txt
echo "child change" >> conflict2.txt
bzr commit -m "Child change"
bzr merge


# Add new file
# Add new directory
echo "new" > new.txt
mkdir new-dir
echo "new-dir-file" > ./new-dir/new-dir-file.txt
bzr add ./new.txt
bzr add ./new-dir

# Delete a file
# delete a directory
bzr rm deleted.txt
# Meld doesn't track this unless there's files below it....
bzr rm deleted-dir

# Rename a file
# Rename a directory
bzr mv renamed.txt renamed-new.txt
# bzr shows the directory as renamed, but not any subfiles. (different to git)
# Meld will not show the directory rename unless there are subfiles.
bzr mv renamed-dir renamed-new-dir

# Modify a file
echo "modified" >> modified.txt
# Modify a directory.... how?

# Change executable bit on file
# Change executable bit on a directory
chmod +x ./exec.txt
# Can't check this... if we -x on owner bzr can't status it anyway.
chmod g-x ./exec-dir

bzr mv ./conflict2.txt ./conflict2-moved.txt
