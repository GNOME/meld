
include ../INSTALL

.PHONY:all
all: meld.desktop meld.schemas

meld.schemas : meld.schemas.in
	intltool-merge -d po $^ $@

meld.schemas.in : meld.schemas.csv
	../tools/csv_to_schema $^ $@

meld.desktop: meld.desktop.in
	intltool-merge -d po $^ $@

.PHONY:clean
clean: 
	-rm -f meld.desktop *.bak meld.schemas.in meld.schemas

.PHONY: install
install: meld.desktop meld.schemas
	mkdir -m 755 -p \
		$(DESTDIR)$(sharedir)/applications \
		$(DESTDIR)$(sharedir)/application-registry \
		$(DESTDIR)$(sharedir)/gconf/schemas
	install -m 644 meld.desktop \
		$(DESTDIR)$(sharedir)/applications
	install -m 644 meld.applications \
		$(DESTDIR)$(sharedir)/application-registry/meld.applications
	install -m 644 meld.schemas \
		$(DESTDIR)$(sharedir)/gconf/schemas/meld.schemas

.PHONY: uninstall
uninstall:
	-rm -rf \
		$(sharedir)/applications/meld.desktop

.PHONY: reinstall-schemas
reinstall-schemas : meld.schemas
	gconftool-2 --recursive-unset /schemas/apps/meld
	gconftool-2 --recursive-unset /apps/meld
	gconftool-2 --install-schema-file meld.schemas
