
.SUFFIXES:

prefix := $(shell grep "^prefix" ../GNUmakefile | cut -d = -f 2)
localedir := $(prefix)/share/locale

PO:=$(wildcard *.po)
MO:=$(PO:.po=/LC_MESSAGES/meld.mo)

.PHONY : all
all : $(MO)

.PHONY : install
install : $(addprefix $(localedir)/,$(MO))

.PHONY : uninstall
uninstall :
	rm -rf $(INST_MO)

.PHONY : clean
clean :
	rm -rf $(PO:.po=)

$(localedir)/%/LC_MESSAGES/meld.mo : %/LC_MESSAGES/meld.mo
	mkdir -m 755 -p $(dir $@) && install -m 644 $<

%/LC_MESSAGES/meld.mo : %.po
	mkdir -m 755 -p $(dir $@) && msgfmt -o $@ $<

