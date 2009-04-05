
.SUFFIXES:

include ../INSTALL

PO:=$(wildcard *.po)
MO:=$(PO:.po=/LC_MESSAGES/meld.mo)
INST_MO:=$(addprefix $(DESTDIR)$(localedir)/,$(MO))

.PHONY : all
all : $(MO)

.PHONY : install
install : $(INST_MO)

.PHONY : uninstall
uninstall :
	rm -rf $(INST_MO)

.PHONY : clean
clean :
	rm -rf $(PO:.po=)

.PHONY : meld.pot
meld.pot:
	intltool-update --pot

## Update .po files
#%.po: meld.pot
#	intltool-update $*

$(DESTDIR)$(localedir)/%/LC_MESSAGES/meld.mo : %/LC_MESSAGES/meld.mo
	mkdir -m 755 -p $(dir $@) && install -m 644 $< $@

%/LC_MESSAGES/meld.mo : %.po
	mkdir -m 755 -p $(dir $@) && msgfmt -c -o $@ $<

