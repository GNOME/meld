
# default install directories
prefix := /usr/local
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
	$(MELD) . ../meld #?.txt
	#$(MELD) ntest/file$(TESTNUM)*
endif

.PHONY:all
all: 
	$(MAKE) -C po

.PHONY:clean
clean: 
	$(MAKE) -C po clean

.PHONY:install
install:
	mkdir -p $(bindir) $(libdir_) $(sharedir_)/glade2/pixmaps $(docdir_) $(sharedir)/applications
	python tools/install_paths libdir=$(libdir_) < meld > meld.install
	install -m 755 meld.install $(bindir)/meld
	rm meld.install
	install -m 644 *.py $(libdir_)
	python tools/install_paths localedir=$(localedir) docdir=$(docdir_) sharedir=$(sharedir_) < paths.py > paths.py.install
	install -m 644 paths.py.install $(libdir_)/paths.py
	rm paths.py.install
	install -m 644 glade2/*.glade $(sharedir_)/glade2
	install -m 644 glade2/pixmaps/*.xpm glade2/pixmaps/*.png $(sharedir_)/glade2/pixmaps
	install -m 755 manual/manual.html $(docdir_)/manual.html
	intltool-merge -d po meld.desktop.in meld.desktop
	install -m 644 meld.desktop $(sharedir)/applications
	$(MAKE) -C po install

.PHONY:uninstall
uninstall:
	rm -rf $(sharedir_) $(docdir_) $(libdir_) $(bindir)/meld $(sharedir)/applications/meld.desktop
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

.PHONY:release
release: check upload announce

.PHONY:update
update:
	cvs -z3 -q update
	
.PHONY:upload
upload:
	cvs tag release-$(subst .,_,$(VERSION))
	scp tools/make_release stevek@master.gnome.org:
	ssh stevek@master.gnome.org python make_release $(VERSION)

.PHONY:announce
announce:
	galeon -n http://freshmeat.net/add-release/29735/ &
	galeon -n http://www.gnome.org/project/admin/newrelease.php?group_id=506 &
	#galeon -n http://sourceforge.net/project/admin/editpackages.php?group_id=53725 &
	
.PHONY:backup
backup:
	tar cvfz ~/archive/meld-`date -I`.tgz .
