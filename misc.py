## python

from __future__ import generators
import errno
import sys
import os
import select

################################################################################
#
# appdir
#
################################################################################
def appdir(path):
    return os.path.join( os.path.dirname(sys.argv[0]), path )

################################################################################
#
# struct
#
################################################################################
class struct:
    def __init__(self, **args):
        self.__dict__.update(args)
    def __repr__(self):
        r = ["<"]
        for i in self.__dict__.keys():
            r.append("%s=%s" % (i, getattr(self,i)))
        r.append(">\n")
        return " ".join(r)

################################################################################
#
# equal
#
################################################################################
def equal(list):
    if len(list):
        first = list[0]
        for n in list[1:]:
            if n != first:
                return 0
    return 1
    
################################################################################
#
# shorten_names
#
################################################################################
def shorten_names(*names):
    """Remove redunant parts of a list of names (e.g. /tmp/foo{1,2} -> foo{1,2}"""
    prefix = os.path.commonprefix( names )
    try:
        prefixslash = prefix.rindex("/") + 1
    except ValueError:
        prefixslash = 0

    names = map( lambda x: x[prefixslash:], names) # remove common prefix
    paths = map( lambda x: x.split("/"), names) # split on /

    try:
        basenames = map(lambda x: x[-1], paths)
    except IndexError:
        pass
    else:
        if equal(basenames):
            def firstpart(list):
                if len(list) > 1: return "[%s] " % list[0]
                else: return ""
            roots = map(firstpart, paths)
            base = basenames[0].strip()
            return [ r+base for r in roots ]
    # no common path. empty names get changed to "[None]"
    return map( lambda x: x or "[None]", names)

################################################################################
#
# look, ilook, all
#
################################################################################
def look(s, o):
    return filter(lambda x:x.find(s)!=-1, dir(o))
def ilook(s, o):
    return filter(lambda x:x.lower().find(s)!=-1, dir(o))
def all(o):
    return "\n".join( ["%s\t%s" % (x,getattr(o,x)) for x in dir(o)] )

################################################################################
#
# system
#
################################################################################
def read_pipe(command, callback=None):
    childin, childout, childerr = os.popen3(command)
    childin.close()
    bits = []
    while len(bits)==0 or bits[-1]!="":
        state = select.select([childout], [], [childout], 0.1)
        if len(state[0])==0:
            if len(state[2])==0:
                if callback:
                    callback()
            else:
                raise "Error reading pipe"
        else:
            try:
                bits.append( childout.read(4096) ) # get buffer size
            except IOError:
                break # ick need to fix
    return "".join(bits)

################################################################################
#
# system
#
################################################################################
def write_pipe(command, text):
    childin, childout, childerr = os.popen3(command, "w")
    childin.write(text)
    childin.close()

################################################################################
#
# safe_apply
#
################################################################################
def safe_apply(object, method, args):
    try:
        m = getattr(object,method)
    except AttributeError:
        pass
    else:
        # allow single arguments to be passed as is.
        if type(args) != type(()):
            args = (args,)
        apply(m, args)

################################################################################
#
# clamp
#
################################################################################
def clamp(val, lower, upper):
    assert lower <= upper
    return min( max(val, lower), upper)

################################################################################
#
# clamp
#
################################################################################
def enumerate(seq):
    i = 0
    for s in seq:
        yield (i,s)
        i += 1

