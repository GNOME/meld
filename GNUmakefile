
# default install directories
prefix := /home/stephen/local
bindir := $(prefix)/bin
libdir := $(prefix)/share/lib
docdir := $(prefix)/share/doc
sharedir := $(prefix)/share
localedir := $(prefix)/share/locale
libdir_ := $(libdir)/meld
docdir_ := $(docdir)/meld
sharedir_ := $(sharedir)/meld

#
VERSION := $(shell grep "^version" meldapp.py | cut -d \"  -f 2)
RELEASE := meld-$(VERSION)
MELD := ./meld #--profile
TESTNUM := 1
DEVELOPER := 0

ifeq ($(DEVELOPER), 1)
.PHONY:rundiff
rundiff: check
	echo $(prefix)
	$(MELD) ?.txt
	#$(MELD) ntest/file$(TESTNUM)*
endif

.PHONY:all
all: 
	$(MAKE) -C po

.PHONY:install
install:
	mkdir -p $(bindir) $(libdir_) $(sharedir_)/glade2/pixmaps $(docdir_)
	python tools/install_paths libdir=$(libdir_) < meld > meld.install
	install -m 755 meld.install $(bindir)/meld
	rm meld.install
	install -m 644 *.py $(libdir_)
	python tools/install_paths localedir=$(localedir) docdir=$(docdir_) sharedir=$(sharedir_) < paths.py > paths.py.install
	install -m 644 paths.py.install $(libdir_)/paths.py
	rm paths.py.install
	install -m 644 glade2/*.glade $(sharedir_)/glade2
	install -m 644 glade2/pixmaps/*.{xpm,png} $(sharedir_)/glade2/pixmaps
	install -m 755 manual/manual.html $(docdir_)/manual.html
	$(MAKE) -C po install

.PHONY:uninstall
uninstall:
	rm -rf $(sharedir_) $(docdir_) $(libdir_) $(bindir)/meld
	$(MAKE) -C po uninstall

.PHONY: test
test:
	$(MELD) ntest/file0{a,b}
	$(MELD) ntest/file5{a,b,c}
	$(MELD) ntest/{1,2}
	$(MELD) ntest/{1,2,3}

.PHONY:changelog
changelog:
	cvs2cl -t

.PHONY:check
check:
	@tools/check_release

.PHONY:gettext
gettext:
	pygettext --keyword=N_ --output-dir=po --default-domain=meld `cat po/POTFILES`

.PHONY:release
release: check upload announce

.PHONY:update
update:
	cvs -z3 -q update
	
.PHONY:upload
upload:
	cvs tag release-$(subst .,_,$(VERSION))
	scp tools/make_release steve9000@meld.sf.net:
	ssh steve9000@meld.sf.net python make_release $(VERSION)

.PHONY:announce
announce:
	galeon -n http://sourceforge.net/project/admin/editpackages.php?group_id=53725 &
	galeon -n http://freshmeat.net/add-release/29735/ &
	galeon -n http://www.gnome.org/project/admin/newrelease.php?group_id=506 &
	
.PHONY:backup
backup:
	tar cvfz ~/archive/meld-`date -I`.tgz .
