## python
import gconf
import gtk

################################################################################
#
# Preferences
#
################################################################################
class Value(object):
    __slots__ = ["type", "default", "current"]
    def __init__(self, t, d):
        self.type = t
        self.default = d
        self.current = d

class ToggleValue(object):
    __slots__ = ["index", "values"]
    def __init__(self, i, v):
        self.index = i
        self.values = v
    def getcurrent(self):
        return self.values[ self.index.current ].current
    current = property(getcurrent)

################################################################################
#
# Preferences
#
################################################################################
class Preferences:
    def __init__(self):
        self.__dict__["gconf"] = gconf.client_get_default()
        self.__dict__["listeners"] = []
        self.__dict__["data"] = {
            "use_custom_font": Value("bool",0),
            "custom_font": Value("string","monospace, 14"),
            "tab_size": Value("int", 4),
            "supply_newline": Value("bool",1),
            "fallback_encoding": Value("string", "latin1"), 
            "draw_style": Value("int",2),
            "toolbar_style": Value("int",0),
            "color_deleted" : Value("string", "#ffffcc"),
            "color_changed" : Value("string", "#ffffcc"),
            "color_edited" : Value("string", "#eeeeee"),
            "color_conflict" : Value("string", "#ffcccc")
            }
        self.gconf.add_dir("/apps/meld", gconf.CLIENT_PRELOAD_NONE)
        self.gconf.notify_add("/apps/meld", self.on_preference_changed)
        for key, value in self.data.items():
            gval = self.gconf.get_without_default("/apps/meld/%s" % key)
            if gval != None:
                value.current = getattr( gval, "get_%s" % value.type )()
            #print key, value.current, gval
    def __getattr__(self, attr):
        #print "get", attr, self.data[attr].current
        return self.data[attr].current
    def __setattr__(self, attr, val):
        value = self.data[attr]
        if value.current != val:
            #print "REALSET", attr, val, value.current
            value.current = val
            setfunc = getattr(self.gconf, "set_%s" % value.type)
            setfunc("/apps/meld/%s" % attr, val)
            for l in self.listeners:
                l(attr,val)
        else:
            #print "fakeset", attr, val, value.current
            pass
    def on_preference_changed(self, client, timestamp, entry, extra):
        attr = entry.key[ entry.key.rindex("/")+1 : ]
        value = self.data[attr]
        val   = getattr(entry.value, "get_%s" % value.type)()
        setattr( self, attr, val)
    def notify_add(self, callback):
        self.listeners.append(callback)
    def dump(self):
        #print self
        for k,v in self.data.items():
            print v
            #print k, v.current
    def get_current_font(self):
        if self.use_custom_font:
            return self.custom_font
        else:
            return self.gconf.get_string('/desktop/gnome/interface/monospace_font_name') or "Monospace 10"
    def get_toolbar_style(self):
        if self.toolbar_style == 0:
            style = self.gconf.get_string('/desktop/gnome/interface/toolbar_style')
            style = {"both":gtk.TOOLBAR_BOTH, "both_horiz":gtk.TOOLBAR_BOTH_HORIZ,
                    "icons":gtk.TOOLBAR_ICONS, "text":gtk.TOOLBAR_TEXT}[style]
        else:
            style = self.toolbar_style - 1
        return style

