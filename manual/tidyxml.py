#! /usr/bin/env python
# tidyxml.py - pretty print an xml file

import sys
import re

tag_begin_re = re.compile("<[^!\?/>]+>")
tag_end_re = re.compile("</[^!\?>]+>")


if len(sys.argv) == 1:
    input = sys.stdin
    output = sys.stdout
elif len(sys.argv) in [2,3]:
    input = open(sys.argv[1])
    if len(sys.argv) == 3:
        output = open(sys.argv[2], "w")
    else:
        output = sys.stdout
else:
    raise "Usage: %s [input [output]]\nPretty print an xml file." % sys.argv[0]

level = [0]
while 1:
    line = input.readline()
    if line == "":
        break
    line = line.strip()
    beg = tag_begin_re.findall(line)
    end = tag_end_re.findall(line)
    if 0:
        print "beg", beg
        print "end", end
        print "cur", level
    if len(beg) and len(beg) >= len(end):
        if level[-1]:
            level.append( len( beg ) - len(end) )
        else:
            level[-1] = len( beg ) - len(end)
    curlevel = len(level) - 1 - (level[-1]==0)
    output.write("%s%s\n" % ("    " * curlevel, line))
    #if len(beg) == 0 and len(end) == 0 and len(level)>1:
    #    curlevel += 1
    foo = len(beg) - len(end)
    while foo < 0:
        level[-1] -= 1
        if level[-1] < 0:
            level.pop()
        foo += 1
