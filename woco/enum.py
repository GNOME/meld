### Copyright (C) 2002-2004 Stephen Kennedy <stevek@gnome.org>

### This program is free software; you can redistribute it and/or modify
### it under the terms of the GNU General Public License as published by
### the Free Software Foundation; either version 2 of the License, or
### (at your option) any later version.

### This program is distributed in the hope that it will be useful,
### but WITHOUT ANY WARRANTY; without even the implied warranty of
### MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
### GNU General Public License for more details.

### You should have received a copy of the GNU General Public License
### along with this program; if not, write to the Free Software
### Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

class EnumMetaClass(type):
    def __init__(cls, name, bases, dict):
        super(EnumMetaClass, cls).__init__(name, bases, dict)
        class Item(object):
            __slots__ = ("name", "value")
            def __init__(self, name, value):
                self.name, self.value = name, value
            def __int__(self):
                return self.value
            def __repr__(self):
                return "<%s %s(%i)>" % (cls.__name__, self.name, self.value)
            def __self__(self):
                return self.name
        cur = 0
        for item in dict["__values__"].split():
            try:
                key,val = item.split("=")
                val = int(val)
            except:
                key = item
                val = cur
            cur = val + 1
            setattr(cls, key, Item(key, val))

class Enum:
    __metaclass__ = EnumMetaClass
    __values__ = ""
