
PROG := ./meld
TESTNUM := 5
VERSION := $(shell python2.2 -c "import meldapp; print meldapp.version")
RELEASE := meld-$(VERSION)

run0 : rundiff
	echo

run1 : runcvs
	echo

rundiff:
#	$(PROG) test/lao test/tzu test/tao
	$(PROG) test/file$(TESTNUM)*

runcvs: 
	(cd .. && meld/$(PROG) meld)
	#(cd ../.. && Projects/meld/$(PROG) Projects/meld)

checkfortabs:
	@grep '	' meld *.py > /dev/null && echo -e '***\n*** TABS DETECTED\n***'

$(RELEASE).tgz: checkfortabs
	cvs tag release-$(subst .,_,$(VERSION))
	cvs -q -z3 export -r release-$(subst .,_,$(VERSION)) -d $(RELEASE) meld
	tar cvfz $(RELEASE).tgz $(RELEASE)
	rm -rf $(RELEASE)

upload: $(RELEASE).tgz
	lftp -c "open upload.sourceforge.net; cd incoming; put $(RELEASE).tgz"

notify:
	galeon -x http://sourceforge.net/project/admin/editpackages.php?group_id=53725 &

release: $(RELEASE).tgz upload notify

