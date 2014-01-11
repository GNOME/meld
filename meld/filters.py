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

import re

from . import misc


class FilterEntry(object):

    __slots__ = ("label", "active", "filter", "filter_string")

    REGEX, SHELL = 0, 1

    def __init__(self, label, active, filter, filter_string):
        self.label = label
        self.active = active
        self.filter = filter
        self.filter_string = filter_string

    @classmethod
    def _compile_regex(cls, regex):
        try:
            compiled = re.compile(regex + "(?m)")
        except re.error:
            compiled = None
        return compiled

    @classmethod
    def _compile_shell_pattern(cls, pattern):
        bits = pattern.split()
        if len(bits) > 1:
            regexes = [misc.shell_to_regex(b)[:-1] for b in bits]
            regex = "(%s)$" % "|".join(regexes)
        elif len(bits):
            regex = misc.shell_to_regex(bits[0])
        else:
            # An empty pattern would match everything, so skip it
            return None

        try:
            compiled = re.compile(regex)
        except re.error:
            compiled = None

        return compiled

    @classmethod
    def parse(cls, string, filter_type):
        elements = string.split("\t")
        if len(elements) < 3:
            return None
        name, active = elements[0], bool(int(elements[1]))
        filter_string = " ".join(elements[2:])
        compiled = FilterEntry.compile_filter(filter_string, filter_type)
        if compiled is None:
            active = False
        return FilterEntry(name, active, compiled, filter_string)

    @classmethod
    def new_from_gsetting(cls, elements, filter_type):
        name, active, filter_string = elements
        compiled = FilterEntry.compile_filter(filter_string, filter_type)
        if compiled is None:
            active = False
        return FilterEntry(name, active, compiled, filter_string)

    @classmethod
    def compile_filter(cls, filter_string, filter_type):
        if filter_type == FilterEntry.REGEX:
            compiled = FilterEntry._compile_regex(filter_string)
        elif filter_type == FilterEntry.SHELL:
            compiled = FilterEntry._compile_shell_pattern(filter_string)
        else:
            raise ValueError("Unknown filter type")
        return compiled

    def __copy__(self):
        new = type(self)(self.label, self.active, None, self.filter_string)
        if self.filter is not None:
            new.filter = re.compile(self.filter.pattern, self.filter.flags)
        return new
