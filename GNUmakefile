
# default install directories
prefix := /usr/local
bindir := $(prefix)/bin
libdir := $(prefix)/lib
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
SPECIALS := meld paths.py

ifeq ($(DEVELOPER), 1)
.PHONY:rundiff
rundiff: check
	echo $(prefix)
	$(MELD) . ../meld #?.txt
	#$(MELD) ntest/file$(TESTNUM)*
endif

.PHONY:all
all: $(addsuffix .install,$(SPECIALS)) meld.desktop
	$(MAKE) -C po

.PHONY:clean
clean: 
	-rm -f *.pyc *.install meld.desktop *.bak glade2/*.bak
	$(MAKE) -C po clean

.PHONY:install
install: $(addsuffix .install,$(SPECIALS)) meld.desktop
	mkdir -p \
		$(DESTDIR)$(bindir) \
		$(DESTDIR)$(libdir_) \
		$(DESTDIR)$(sharedir_)/glade2/pixmaps \
		$(DESTDIR)$(docdir_) \
		$(DESTDIR)$(sharedir)/applications \
		$(DESTDIR)$(sharedir)/application-registry \
		$(DESTDIR)$(sharedir)/pixmaps
	install -m 755 meld.install \
		$(DESTDIR)$(bindir)/meld
	install -m 644 *.py \
		$(DESTDIR)$(libdir_)
	install -m 644 paths.py.install \
		$(DESTDIR)$(libdir_)/paths.py
	install -m 644 meld.applications \
		$(DESTDIR)$(sharedir)/application-registry/meld.applications
	install -m 644 meld.desktop \
		$(DESTDIR)$(sharedir)/applications
	python    -c 'import compileall; compileall.compile_dir("$(DESTDIR)$(libdir_)")'
	python -O -c 'import compileall; compileall.compile_dir("$(DESTDIR)$(libdir_)")'
	install -m 644 \
		glade2/*.glade \
		$(DESTDIR)$(sharedir_)/glade2
	install -m 644 \
		glade2/pixmaps/*.xpm \
		glade2/pixmaps/*.png \
		$(DESTDIR)$(sharedir_)/glade2/pixmaps
	install -m 755 \
		manual/manual.html \
		$(DESTDIR)$(docdir_)/manual.html
	install -m 644 glade2/pixmaps/icon.png \
		$(DESTDIR)$(sharedir)/pixmaps/meld.png
	$(MAKE) -C po install

meld.desktop: meld.desktop.in
	intltool-merge -d po meld.desktop.in meld.desktop

%.install: %
	python tools/install_paths \
		libdir=$(libdir_) \
		localedir=$(localedir) \
		docdir=$(docdir_) \
		sharedir=$(sharedir_) \
		< $< > $@

.PHONY:uninstall
uninstall:
	-rm -rf \
		$(sharedir_) \
		$(docdir_) \
		$(libdir_) \
		$(bindir)/meld \
		$(sharedir)/applications/meld.desktop \
		$(sharedir)/pixmaps/meld.png
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
