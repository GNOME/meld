
.SUFFIXES :

# default install directories
include INSTALL

#
VERSION := $(shell grep "^version" meldapp.py | cut -d \"  -f 2)
RELEASE := meld-$(VERSION)
MELD_CMD := ./meld #--profile
TESTNUM := 1
DEVELOPER := 0
SPECIALS := meld paths.py
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
	-rm -f *.pyc vc/*.pyc *.install meld.desktop *.bak glade2/*.bak
	$(MAKE) -C po clean
	$(MAKE) -C help clean

.PHONY:install
install: $(addsuffix .install,$(SPECIALS)) meld.desktop
	mkdir -m 755 -p \
		$(DESTDIR)$(bindir) \
		$(DESTDIR)$(libdir_) \
		$(DESTDIR)$(libdir_)/vc \
		$(DESTDIR)$(sharedir_)/glade2/pixmaps \
		$(DESTDIR)$(docdir_) \
		$(DESTDIR)$(sharedir)/applications \
		$(DESTDIR)$(sharedir)/pixmaps \
		$(DESTDIR)$(helpdir_)
	install -m 755 meld.install \
		$(DESTDIR)$(bindir)/meld
	install -m 644 *.py \
		$(DESTDIR)$(libdir_)
	install -m 644 vc/*.py \
		$(DESTDIR)$(libdir_)/vc
	install -m 644 paths.py.install \
		$(DESTDIR)$(libdir_)/paths.py
	install -m 644 meld.desktop \
		$(DESTDIR)$(sharedir)/applications
	$(PYTHON)    -c 'import compileall; compileall.compile_dir("$(DESTDIR)$(libdir_)",10,"$(libdir_)")'
	$(PYTHON) -O -c 'import compileall; compileall.compile_dir("$(DESTDIR)$(libdir_)",10,"$(libdir_)")'
	install -m 644 \
		glade2/*.glade \
		$(DESTDIR)$(sharedir_)/glade2
	install -m 644 \
		glade2/*.xml \
		$(DESTDIR)$(sharedir_)/glade2
	install -m 644 \
		glade2/pixmaps/*.xpm \
		glade2/pixmaps/*.png \
		$(DESTDIR)$(sharedir_)/glade2/pixmaps
	install -m 644 glade2/pixmaps/icon.png \
		$(DESTDIR)$(sharedir)/pixmaps/meld.png
	$(MAKE) -C po install
	$(MAKE) -C help install

meld.desktop: meld.desktop.in
	intltool-merge -d po meld.desktop.in meld.desktop

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
	$(BROWSER) http://freshmeat.net/add-release/29735/ &
	$(BROWSER) http://www.gnomefiles.org/devs/newversion.php?soft_id=203 &
	$(BROWSER) http://www.gnome.org/project/admin/newrelease.php?group_id=506 &
	$(BROWSER) http://sourceforge.net/project/admin/editpackages.php?group_id=53725 &
	
.PHONY:update
update:
	svn update
	
.PHONY:backup
backup:
	tar cvfz ~/archive/meld-`date -I`.tgz --exclude='*.pyc' --exclude='*.bak' --exclude='*.swp' .
	@echo Created ~/archive/meld-`date -I`.tgz
