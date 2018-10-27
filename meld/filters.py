# Copyright (C) 2011-2013 Kai Willadsen <kai.willadsen@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or (at
# your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import re

log = logging.getLogger(__name__)


def try_compile(regex, flags=0):
    try:
        compiled = re.compile(regex, flags)
    except re.error:
        log.warning(
            'Error compiling regex {!r} with flags {!r}'.format(regex, flags))
        compiled = None
    return compiled


class FilterEntry:

    __slots__ = ("label", "active", "filter", "byte_filter", "filter_string")

    REGEX, SHELL = 0, 1

    def __init__(self, label, active, filter, byte_filter, filter_string):
        self.label = label
        self.active = active
        self.filter = filter
        self.byte_filter = byte_filter
        self.filter_string = filter_string

    @classmethod
    def compile_regex(cls, regex, byte_regex=False):
        if byte_regex and not isinstance(regex, bytes):
            # TODO: Register a custom error handling function to replace
            # encoding errors with '.'?
            regex = regex.encode('utf8', 'replace')
        return try_compile(regex, re.M)

    @classmethod
    def compile_shell_pattern(cls, pattern):
        bits = pattern.split()
        if not bits:
            # An empty pattern would match everything, so skip it
            return None
        elif len(bits) > 1:
            regexes = [shell_to_regex(b)[:-1] for b in bits]
            regex = "(%s)$" % "|".join(regexes)
        else:
            regex = shell_to_regex(bits[0])
        return try_compile(regex)

    @classmethod
    def new_from_gsetting(cls, elements, filter_type):
        name, active, filter_string = elements
        if filter_type == cls.REGEX:
            str_re = cls.compile_regex(filter_string)
            bytes_re = cls.compile_regex(filter_string, byte_regex=True)
        elif filter_type == cls.SHELL:
            str_re = cls.compile_shell_pattern(filter_string)
            bytes_re = None
        else:
            raise ValueError("Unknown filter type")

        active = active and bool(str_re)
        return cls(name, active, str_re, bytes_re, filter_string)

    @classmethod
    def check_filter(cls, filter_string, filter_type):
        if filter_type == cls.REGEX:
            compiled = cls.compile_regex(filter_string)
        elif filter_type == cls.SHELL:
            compiled = cls.compile_shell_pattern(filter_string)
        return compiled is not None

    def __copy__(self):
        new = type(self)(
            self.label, self.active, None, None, self.filter_string)
        if self.filter is not None:
            new.filter = re.compile(self.filter.pattern, self.filter.flags)
        if self.byte_filter is not None:
            new.byte_filter = re.compile(
                self.byte_filter.pattern, self.byte_filter.flags)
        return new


def shell_to_regex(pat):
    """Translate a shell PATTERN to a regular expression.

    Based on fnmatch.translate().
    We also handle {a,b,c} where fnmatch does not.
    """

    i, n = 0, len(pat)
    res = ''
    while i < n:
        c = pat[i]
        i += 1
        if c == '\\':
            try:
                c = pat[i]
            except IndexError:
                pass
            else:
                i += 1
                res += re.escape(c)
        elif c == '*':
            res += '.*'
        elif c == '?':
            res += '.'
        elif c == '[':
            try:
                j = pat.index(']', i)
            except ValueError:
                res += r'\['
            else:
                stuff = pat[i:j]
                i = j + 1
                if stuff[0] == '!':
                    stuff = '^%s' % stuff[1:]
                elif stuff[0] == '^':
                    stuff = r'\^%s' % stuff[1:]
                res += '[%s]' % stuff
        elif c == '{':
            try:
                j = pat.index('}', i)
            except ValueError:
                res += '\\{'
            else:
                stuff = pat[i:j]
                i = j + 1
                res += '(%s)' % "|".join(
                    [shell_to_regex(p)[:-1] for p in stuff.split(",")]
                )
        else:
            res += re.escape(c)
    return res + "$"
