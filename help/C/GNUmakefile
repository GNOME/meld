
.SUFFIXES :
include ../../INSTALL

LANG := $(notdir $(CURDIR))
XML_DIR_ := $(helpdir_)/$(LANG)
OMF_NAME := meld-$(LANG).omf
OMF_DIR_ := $(sharedir)/omf/meld

.PHONY : all
all $(OMF_NAME) : $(OMF_NAME).in
	scrollkeeper-preinstall $(XML_DIR_)/meld.xml $(OMF_NAME).in $(OMF_NAME)

.PHONY : install
install : $(OMF_NAME)
	mkdir -m 755 -p $(DESTDIR)$(OMF_DIR_) $(DESTDIR)$(XML_DIR_) $(DESTDIR)$(XML_DIR_)/figures
	install -m 644 meld.xml $(DESTDIR)$(XML_DIR_)/meld.xml
	install -m 644 figures/*.png $(DESTDIR)$(XML_DIR_)/figures
	install -m 644 $(OMF_NAME) $(DESTDIR)$(OMF_DIR_)/$(OMF_NAME)
	-scrollkeeper-install $(DESTDIR)$(OMF_DIR_)/$(OMF_NAME)

.PHONY : uninstall
uninstall :
	-scrollkeeper-uninstall $(OMF_DIR_)/$(OMF_NAME)
	-rm -f $(OMF_DIR_)/$(OMF_NAME) \
		$(XML_DIR_)/meld.xml \
		$(XML_DIR_)/figures/*.png
	-rmdir $(XML_DIR_)/figures \
		$(XML_DIR_)

.PHONY : clean
clean :
	-rm -f $(OMF_NAME)

