#! /bin/sh
# generate meld.pot
intltool-update -g meld -p
# remove garbage comments
cp meld.pot meld.pot.in && cat meld.pot.in | sed -e "/^#\..*/d" > meld.pot
rm meld.pot.in