
PROG=./meld
TESTNUM=3
VERSION=0.5.1
RELEASE=meld-$(VERSION)

run : rundiff

rundiff:
	$(PROG) test/lao test/tzu test/tao
#	$(PROG) test/file$(TESTNUM)*

runcvs: 
	(cd . && $(PROG) .)
	#(cd .. && meld/$(PROG) meld)
	#(cd ../.. && Projects/meld/$(PROG) Projects/meld)

$(RELEASE).tgz:
	cvs tag release-$(subst .,_,$(VERSION))
	cvs -q -z3 export -d $(RELEASE) -r release-$(subst .,_,$(VERSION))
	tar cvfz $(RELEASE).tgz $(RELEASE)
	rm -rf $(RELEASE)

upload: $(RELEASE).tgz
	lftp -c "open upload.sourceforge.net; cd incoming; put $(RELEASE).tgz"

notify:
	galeon -x http://sourceforge.net/project/admin/editpackages.php?group_id=53725 &

release: $(RELEASE).tgz upload notify
