#! /bin/sh

if [ $# -lt 1 ]; then
	echo "Update which language?"
	exit 1
fi

for lang in $*; do
	echo updating $lang
	intltool-update -g meld $lang
done
