
NUM=2
VERSION=0.3
RELEASE=meld-$(VERSION)

run:
	./meld.py test/file$(NUM)a test/file$(NUM)b

$(RELEASE).tgz:
	cvs -q -z3 export -d $(RELEASE) -D now meld
	tar cvfz $(RELEASE).tgz $(RELEASE)
	rm -rf $(RELEASE)

upload: $(RELEASE).tgz
	lftp -c "open upload.sourceforge.net; cd incoming; put $(RELEASE).tgz"

notify:
	galeon -x http://sourceforge.net/project/admin/editpackages.php?group_id=53725

release: $(RELEASE).tgz upload notify
