
PO:=$(wildcard *.po)
GMO:=$(PO:.po=/LC_MESSAGES/meld.mo)
DIRS:=$(PO:.po=/LC_MESSAGES)

.PHONY:all
all: $(DIRS) $(GMO)

%/LC_MESSAGES/meld.mo : %.po
	msgfmt -o $@ $*.po

%/LC_MESSAGES : 
	mkdir -p $@

.PHONY:update-po
update-po:
	@make -C .. gettext
	python ./update-po.py
