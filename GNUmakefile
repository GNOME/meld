
PROG := ./meld #--profile
TESTNUM := 1
VERSION := $(shell grep "^version" meldapp.py | cut -d \"  -f 2)
RELEASE := meld-$(VERSION)

run : check rundiff
	@echo

rundiff:
	#$(PROG) .
	#$(PROG) scratch*
	#$(PROG) ../old/meld-2003-03-01 . #../old/meld-2002-12-21
	#$(PROG) test/lao test/tzu test/tao
	#$(PROG) hkBaseSystem.cpp hkBaseSystem.cpp
	$(PROG) ntest/file$(TESTNUM)*
	#$(PROG) ../old/meld-2002-11-12 .
	#$(PROG) {../old/oldmeld,../svnrepository/meld}/GNUmakefile
	#$(PROG) test/1 test/2
	#$(PROG) /zip/meld .

check:
	@check_release

release: check upload announce

upload:
	cvs tag release-$(subst .,_,$(VERSION))
	ssh steve9000@meld.sf.net python make_release $(VERSION)

announce:
	galeon -n http://sourceforge.net/project/admin/editpackages.php?group_id=53725 &
	galeon -n http://freshmeat.net/add-release/29735/ &
	galeon -n http://www.gnome.org/project/admin/newrelease.php?group_id=506 &
	
backup:
	tar cvfz ~/archive/meld-`date -I`.tgz .
