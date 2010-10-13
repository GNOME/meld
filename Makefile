
.SUFFIXES :

# default install directories
include INSTALL

#
VERSION := $(shell grep "^version" meld/meldapp.py | cut -d \"  -f 2)
RELEASE := meld-$(VERSION)
MELD_CMD := ./meld #--profile
TESTNUM := 1
DEVELOPER := 0
SPECIALS := bin/meld meld/paths.py
BROWSER := firefox

ifeq ($(DEVELOPER), 1)
.PHONY:rundiff
rundiff: check
	echo $(prefix)
	$(MELD_CMD) . ../meld #?.txt
	#$(MELD_CMD) ntest/file$(TESTNUM)*
	#./meld {.,../old/dev/meld}/meld
endif

.PHONY:all
all: $(addsuffix .install,$(SPECIALS)) meld.desktop
	$(MAKE) -C po
	$(MAKE) -C help

.PHONY:clean
clean: 
	@find ./meld -type f \( -name '*.pyc' -o -name '*.install' \) -print0 |\
		xargs -0 rm -f
	@find ./bin -type f \( -name '*.install' \) -print0 | xargs -0 rm -f
	@rm -f data/meld.desktop
	$(MAKE) -C po clean
	$(MAKE) -C help clean

.PHONY:install
install: $(addsuffix .install,$(SPECIALS)) meld.desktop
	mkdir -m 755 -p \
		$(DESTDIR)$(bindir) \
		$(DESTDIR)$(libdir_) \
		$(DESTDIR)$(libdir_)/meld \
		$(DESTDIR)$(libdir_)/meld/ui \
		$(DESTDIR)$(libdir_)/meld/util \
		$(DESTDIR)$(libdir_)/meld/vc \
		$(DESTDIR)$(sharedir_)/ui \
		$(DESTDIR)$(sharedir_)/icons \
		$(DESTDIR)$(docdir_) \
		$(DESTDIR)$(sharedir)/applications \
		$(DESTDIR)$(sharedir)/pixmaps \
		$(DESTDIR)$(sharedir)/icons/hicolor/16x16/apps \
		$(DESTDIR)$(sharedir)/icons/hicolor/22x22/apps \
		$(DESTDIR)$(sharedir)/icons/hicolor/32x32/apps \
		$(DESTDIR)$(sharedir)/icons/hicolor/48x48/apps \
		$(DESTDIR)$(sharedir)/icons/hicolor/scalable/apps \
		$(DESTDIR)$(helpdir_)
	install -m 755 bin/meld.install \
		$(DESTDIR)$(bindir)/meld
	install -m 644 meld/*.py \
		$(DESTDIR)$(libdir_)/meld
	install -m 644 meld/ui/*.py \
		$(DESTDIR)$(libdir_)/meld/ui
	install -m 644 meld/util/*.py \
		$(DESTDIR)$(libdir_)/meld/util
	install -m 644 meld/vc/*.py \
		$(DESTDIR)$(libdir_)/meld/vc
	install -m 644 meld/paths.py.install \
		$(DESTDIR)$(libdir_)/meld/paths.py
	install -m 644 data/meld.desktop \
		$(DESTDIR)$(sharedir)/applications
	$(PYTHON)    -c 'import compileall; compileall.compile_dir("$(DESTDIR)$(libdir_)",10,"$(libdir_)")'
	$(PYTHON) -O -c 'import compileall; compileall.compile_dir("$(DESTDIR)$(libdir_)",10,"$(libdir_)")'
	install -m 644 \
		data/ui/*.ui \
		$(DESTDIR)$(sharedir_)/ui
	install -m 644 \
		data/ui/*.xml \
		$(DESTDIR)$(sharedir_)/ui
	install -m 644 \
		data/icons/*.xpm \
		data/icons/*.png \
		$(DESTDIR)$(sharedir_)/icons
	install -m 644 data/icons/icon.png \
		$(DESTDIR)$(sharedir)/pixmaps/meld.png
	install -m 644 data/icons/16x16/meld.png \
		$(DESTDIR)$(sharedir)/icons/hicolor/16x16/apps/meld.png
	install -m 644 data/icons/22x22/meld.png \
		$(DESTDIR)$(sharedir)/icons/hicolor/22x22/apps/meld.png
	install -m 644 data/icons/32x32/meld.png \
		$(DESTDIR)$(sharedir)/icons/hicolor/32x32/apps/meld.png
	install -m 644 data/icons/48x48/meld.png \
		$(DESTDIR)$(sharedir)/icons/hicolor/48x48/apps/meld.png
	install -m 644 data/icons/48x48/meld.svg \
		$(DESTDIR)$(sharedir)/icons/hicolor/scalable/apps/meld.svg
	$(MAKE) -C po install
	$(MAKE) -C help install

meld.desktop: data/meld.desktop.in
	intltool-merge -d po data/meld.desktop.in data/meld.desktop

%.install: %
	$(PYTHON) tools/install_paths \
		libdir=$(libdir_) \
		localedir=$(localedir) \
		helpdir=$(helpdir_) \
		sharedir=$(sharedir_) \
		< $< > $@

.PHONY:uninstall
uninstall:
	-rm -rf \
		$(sharedir_) \
		$(docdir_) \
		$(helpdir_) \
		$(libdir_) \
		$(bindir)/meld \
		$(sharedir)/applications/meld.desktop \
		$(sharedir)/pixmaps/meld.png
	$(MAKE) -C po uninstall
	$(MAKE) -C help uninstall

.PHONY: test
test:
	$(MELD_CMD) ntest/file0{a,b}
	$(MELD_CMD) ntest/file5{a,b,c}
	$(MELD_CMD) ntest/{1,2}
	$(MELD_CMD) ntest/{1,2,3}

.PHONY:changelog
changelog:
	# need to find the most recently tagged version automatically
	svn2cl -r 1083:HEAD

.PHONY:release
release: check tag upload announce

.PHONY:check
check:
	@tools/check_release

.PHONY:tag
tag:
	svn cp -m "Tagged." svn+ssh://stevek@svn.gnome.org/svn/meld/trunk svn+ssh://stevek@svn.gnome.org/svn/meld/tags/release-$(subst .,_,$(VERSION))

.PHONY:upload
upload:
	scp tools/make_release stevek@master.gnome.org:
	ssh stevek@master.gnome.org python make_release $(VERSION)

.PHONY:announce
announce:
	$(BROWSER) http://freshmeat.net/projects/meld/releases/new
	$(BROWSER) http://www.gnomefiles.org/devs/newversion.php?soft_id=203 &
	$(BROWSER) http://sourceforge.net/project/admin/editpackages.php?group_id=53725 &
	#$(BROWSER) http://www.gnome.org/project/admin/newrelease.php?group_id=506 &
	
.PHONY:update
update:
	svn update
	
.PHONY:backup
backup:
	tar cvfz ~/archive/meld-`date -I`.tgz --exclude='*.pyc' --exclude='*.bak' --exclude='*.swp' .
	@echo Created ~/archive/meld-`date -I`.tgz
