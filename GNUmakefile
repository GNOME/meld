
PROG := ./meld #--profile
TESTNUM := 8
VERSION := $(shell grep "^version" meldapp.py | cut -d \"  -f 2)
RELEASE := meld-$(VERSION)

.PHONY:run
run : check rundiff
	@echo

.PHONY:rundiff
rundiff:
	#$(PROG) .
	$(PROG) foo?
	#$(PROG) ../old/meld-2003-05-02 . #../old/meld-2002-12-21
	#$(PROG) test/lao test/tzu test/tao
	#$(PROG) ntest/file$(TESTNUM)*
	#$(PROG) ntest/file$(TESTNUM)a ntest/file$(TESTNUM)a
	#$(PROG) ../old/meld-2003-05-02/ .
	#$(PROG) {../old/oldmeld,../svnrepository/meld}/GNUmakefile
	#$(PROG) test/1 test/2
	#$(PROG) /zip/meld .

.PHONY:ChangeLog
ChangeLog:
	cvs2cl -t

.PHONY:check
check:
	@check_release

.PHONY:gettext
gettext:
	pygettext --keyword=N_ --output-dir=po --default-domain=meld `cat po/POTFILES`

.PHONY:release
release: check upload announce

.PHONY:update
update:
	cvs update
	
.PHONY:upload
upload:
	cvs tag release-$(subst .,_,$(VERSION))
	ssh steve9000@meld.sf.net python make_release $(VERSION)

.PHONY:announce
announce:
	galeon -n http://sourceforge.net/project/admin/editpackages.php?group_id=53725 &
	galeon -n http://freshmeat.net/add-release/29735/ &
	galeon -n http://www.gnome.org/project/admin/newrelease.php?group_id=506 &
	
.PHONY:backup
backup:
	tar cvfz ~/archive/meld-`date -I`.tgz .
