#! /usr/bin/env python
import os
po = [x for x in os.listdir(".") if x.endswith(".po")]
for p in po:
	mo = os.popen("msgmerge %s meld.pot" % p).read()
	if mo != open(p).read():
		print "Updated", p,
		open(p,"w").write(mo)
