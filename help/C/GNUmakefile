
.SUFFIXES :
include ../../INSTALL

LANG := $(notdir $(CURDIR))
XML_DIR_ := $(DESTDIR)$(helpdir_)/$(LANG)
OMF_NAME := meld-$(LANG).omf
OMF_DIR_ := $(DESTDIR)$(sharedir)/omf/meld

.PHONY : all
all $(OMF_NAME) : $(OMF_NAME).in
	scrollkeeper-preinstall $(XML_DIR_)/meld.xml $(OMF_NAME).in $(OMF_NAME)

.PHONY : install
install : $(OMF_NAME)
	mkdir -m 755 -p $(OMF_DIR_) $(XML_DIR_) $(XML_DIR_)/figures
	install -m 644 meld.xml $(XML_DIR_)/meld.xml
	install -m 644 figures/*.png $(XML_DIR_)/figures
	install -m 644 $(OMF_NAME) $(OMF_DIR_)/$(OMF_NAME)
	scrollkeeper-install $(OMF_DIR_)/$(OMF_NAME)

.PHONY : uninstall
uninstall :
	scrollkeeper-uninstall $(OMF_DIR_)/$(OMF_NAME)
	-rm -f $(OMF_DIR_)/$(OMF_NAME) \
		$(XML_DIR_)/meld.xml \
		$(XML_DIR_)/figures/*.png
	-rmdir $(XML_DIR_)/figures \
		$(XML_DIR_)

.PHONY : clean
clean :
	-rm -f $(OMF_NAME)

