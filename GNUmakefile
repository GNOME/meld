
PROG=./meld
TESTNUM=3
VERSION=0.5.0
RELEASE=meld-$(VERSION)

run: 
#	$(PROG) test/lao test/tzu test/tao
#	./niff3.py
#	$(PROG) test/file$(TESTNUM)*
	$(PROG) .

$(RELEASE).tgz:
	cvs -q -z3 export -d $(RELEASE) -D now meld
	tar cvfz $(RELEASE).tgz $(RELEASE)
	rm -rf $(RELEASE)

upload: $(RELEASE).tgz
	lftp -c "open upload.sourceforge.net; cd incoming; put $(RELEASE).tgz"

notify:
	galeon -x http://sourceforge.net/project/admin/editpackages.php?group_id=53725

release: $(RELEASE).tgz upload notify
