
PROG := ./meld
TESTNUM := 5
VERSION := $(shell python2.2 -c "import meldapp; print meldapp.version")
RELEASE := meld-$(VERSION)

#run0 : rundiff
	#echo

run1 : runcvs
	echo

rundiff:
#	$(PROG) test/lao test/tzu test/tao
	$(PROG) test/file$(TESTNUM)*

runcvs: 
	meld ..
	#(cd .. && meld/$(PROG) meld)
	#(cd ../.. && Projects/meld/$(PROG) Projects/meld)

#checkfortabs:
#	grep '	' meld *.py > /dev/null && echo -e '***\n*** TABS DETECTED\n***'

release: 
	cvs tag release-$(subst .,_,$(VERSION))
	ssh steve9000@meld.sf.net python make_release $(VERSION)
	galeon -x http://sourceforge.net/project/admin/editpackages.php?group_id=53725 &

