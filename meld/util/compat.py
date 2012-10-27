
import sys

# Python 2/3 compatibility, named as per six
text_type = str if sys.version_info[0] == 3 else unicode
string_types = str if sys.version_info[0] == 3 else basestring
