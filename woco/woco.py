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

class Entry(object):
    def __init__(self, path, status=Status.UNVERSIONED, tag="", version="" ):
        self.path = path
        self.status = status
        self.tag = tag
        self.version = version
    def __repr__(self):
        return "%s %s\n" % (self.path, self.status)
    def __cmp__(self, entry):
        return cmp(self.path, entry.path)

def shell_to_regex(pat):
    """Translate a shell PATTERN to a regular expression.

    Based on fnmatch.translate(). We also handle {a,b,c} where fnmatch does not.
    There is no way to quote meta-characters.
    """

    i, n = 0, len(pat)
    res = ''
    while i < n:
        c = pat[i]
        i = i+1
        if c == '*':
            res += '.*'
        elif c == '?':
            res += '.'
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
        elif c == '{':
            try:
                j = pat.index('}', i)
                stuff = pat[i:j]
                i = j+1
                res += '(%s)' % "|".join([shell_to_regex(p)[:-1] for p in stuff.split(",")])
            except ValueError:
                res += '\\{'
        else:
            res += re.escape(c)
    return res + "$"
