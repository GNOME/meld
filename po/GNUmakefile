
prefix := $(shell grep "^prefix" ../GNUmakefile | cut -d = -f 2)
localedir := $(prefix)/share/locale

PO:=$(wildcard *.po)
MO:=$(PO:.po=/LC_MESSAGES/meld.mo)
DIRS:=$(PO:.po=/LC_MESSAGES)
INST_MO:=$(addprefix $(localedir)/,$(MO))

.PHONY : all
all : $(DIRS) $(MO)

.PHONY : install
install : all $(INST_MO)

.PHONY : uninstall
uninstall :
	rm -rf $(INST_MO)

.PHONY : clean
clean :
	rm -rf $(PO:.po=)

$(localedir)/%/LC_MESSAGES/meld.mo : %/LC_MESSAGES/meld.mo
	mkdir -m 755 -p $(dir $@) && install -m 644 $^ $@

%/LC_MESSAGES/meld.mo : %.po
	msgfmt -o $@ $*.po

%/LC_MESSAGES : 
	mkdir -p $@

.PHONY:update-po
update-po:
	@make -C .. gettext
	python ./update-po.py
