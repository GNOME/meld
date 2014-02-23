
.SUFFIXES :

LANGUAGES := C el es fr

.PHONY : all install uninstall clean

all install uninstall clean : 
	for lang in $(LANGUAGES); do \
		$(MAKE) -C $$lang $@ ; \
	done

