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

"""Commonly used undo/redo actions

Use with undo.UndoSequence()
"""

class TextBufferInsert(object):
    def __init__(self, buffer, offset, text):
        self.buffer = buffer
        self.offset = offset 
        self.text = text
    def undo(self):
        b = self.buffer
        b.delete( b.get_iter_at_offset( self.offset), b.get_iter_at_offset(self.offset + len(self.text)) )
    def redo(self):
        b = self.buffer
        b.insert( b.get_iter_at_offset( self.offset), self.text) 

class TextBufferDelete(object):
    def __init__(self, buffer, offset, text):
        self.buffer = buffer
        self.offset = offset 
        self.text = text
    def undo(self):
        b = self.buffer
        b.insert( b.get_iter_at_offset( self.offset), self.text) 
    def redo(self):
        b = self.buffer
        b.delete( b.get_iter_at_offset( self.offset), b.get_iter_at_offset(self.offset + len(self.text)) )

class TextBufferModify(object):
    def __init__(self, buffer):
        self.buffer = buffer
        self.buffer.set_modified(1)
    def undo(self):
        self.buffer.set_modified(0)
    def redo(self):
        self.buffer.set_modified(1)

