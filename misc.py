
import sys
import os

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
# shorten_names
#
################################################################################
def shorten_names(*names):
    """Remove redunant parts of a list of names (e.g. /tmp/foo{1,2} -> foo{1,2}"""
    prefix = os.path.commonprefix( filter(lambda x: x, names) )
    lastslash = prefix.rfind("/") + 1
    if lastslash != 0:
        # strip leading path from name. empty names get changed to "[None]"
        return [ (n[lastslash:],"[None]")[n.strip()==""] for n in names ]
    else:
        # no common path. empty names get changed to "[None]"
        return map( lambda x: x or "[None]", names)

################################################################################
#
# look, ilook
#
################################################################################
def look(s, o):
    return filter(lambda x:x.find(s)!=-1, dir(o))
def ilook(s, o):
    return filter(lambda x:x.lower().find(s)!=-1, dir(o))

