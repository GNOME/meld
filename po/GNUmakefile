
.SUFFIXES:

prefix := $(strip $(shell grep "^prefix" ../GNUmakefile | cut -d = -f 2))
localedir := $(prefix)/share/locale

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

$(DESTDIR)$(localedir)/%/LC_MESSAGES/meld.mo : %/LC_MESSAGES/meld.mo
	mkdir -m 755 -p $(dir $@) && install -m 644 $< $@

%/LC_MESSAGES/meld.mo : %.po
	mkdir -m 755 -p $(dir $@) && msgfmt -c -o $@ $<

