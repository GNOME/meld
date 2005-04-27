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

import enum
import re

__metaclass__ = type

class Status(enum.Enum):
    """
    "Normal" Checked out and unchanged
    "Ignored" Explicitly ignored (i.e. .cvsignore)
    "Unversioned" Exists locally but not added to repository
    "Newly added" Added locally but not yet committed
    "Modified" Locally modified
    "Conflict" Contains merge conflict
    "Removed" Removed from control and local filesystem
    "Missing" Checked out but missing from local filesystem
    """
    __values__ = "UNVERSIONED NORMAL IGNORED NEW MODIFIED CONFLICT REMOVED MISSING"

class Entry:

    __slots__ = ("path", "isdir", "status", "tag", "version")

    def __init__(self, path, isdir=False, status=Status.UNVERSIONED, tag="", version="" ):
        self.path = path
        self.isdir = isdir
        self.status = status
        self.tag = tag
        self.version = version
    def __repr__(self):
        return "%s %s\n" % (self.path, self.status)
    def __cmp__(self, entry):
        return cmp(self.path, entry.path)

def shell_to_regex(pat, extended=True):
    """Translate a shell PATTERN to a regular expression.

    Based on fnmatch.translate(). We also handle {a,b,c} if extended is true.
    """

    i, n = 0, len(pat)
    last = None
    res = ''
    while i < n:
        c = pat[i]
        i = i+1
        if last == '\\':
            res += c
        elif c == '*':
            res += '.*'
        elif c == '?':
            res += '.'
        elif c == '\\':
            res += c
        elif c == '[':
            try:
                j = pat.index(']', i)
                stuff = pat[i:j]
                i = j+1
                if stuff[0] == '!':
                    stuff = '^%s' % stuff[1:]
                elif stuff[0] == '^':
                    stuff = r'\^%s' % stuff[1:]
                res += '[%s]' % stuff
            except ValueError:
                res += r'\['
        elif c == '{' and extended:
            try:
                j = pat.index('}', i)
                stuff = pat[i:j]
                i = j+1
                res += '(%s)' % "|".join([shell_to_regex(p)[:-1] for p in stuff.split(",")])
            except ValueError:
                res += r'\{'
        else:
            res += re.escape(c)
        last = c
    return res + "$"

def test():
    tre = shell_to_regex("{arch}", extended=False)
    print tre
    cre = re.compile(tre)
    print cre.search("{arch}")

if __name__ == "__main__":
    test()
