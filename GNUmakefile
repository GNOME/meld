
PROG := ./meld
TESTNUM := 5
VERSION := $(shell python2.2 -c "import meldapp; print meldapp.version")
RELEASE := meld-$(VERSION)

run : rundiff
	@echo

rundiff:
#	$(PROG) test/lao test/tzu test/tao
#	$(PROG) test/file$(TESTNUM)*
	$(PROG) ../old/oldmeld ../svnrepository/meld
#	$(PROG) {../old/oldmeld,../svnrepository/meld}/GNUmakefile

#checkfortabs:
#	grep '	' meld *.py > /dev/null && echo -e '***\n*** TABS DETECTED\n***'

release: 
	cvs tag release-$(subst .,_,$(VERSION))
	ssh steve9000@meld.sf.net python make_release $(VERSION)
	galeon -x http://sourceforge.net/project/admin/editpackages.php?group_id=53725 &
	galeon -x http://www.gnome.org/project/admin/newrelease.php?group_id=506 &
	
backup:
	tar cvfz ~/archive/meld-`date -I`.tgz .
