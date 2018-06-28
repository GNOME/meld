import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gdk
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango

GObjectModule = gi.module.get_introspection_module('GObject')

TYPE_PANGO_WEIGHT = GObjectModule.type_from_name('PangoWeight')
TYPE_PANGO_STYLE = GObjectModule.type_from_name('PangoStyle')
TYPE_GDK_RGBA = GObjectModule.type_from_name('GdkRGBA')


class GString(GObject.Value):
    def __init__(self, py_value):
        GObjectModule.Value.__init__(self)
        if not isinstance(py_value, str):
            raise ValueError('Expected string but got "%s" "%s"' %
                    (py_value, type(py_value)))
        self.init(GObject.TYPE_STRING)
        self.set_string(py_value)


class GBool(GObject.Value):
    def __init__(self, py_value):
        GObjectModule.Value.__init__(self)
        self.init(GObject.TYPE_BOOLEAN)
        self.set_boolean(bool(py_value))


class GPyObject(GObject.Value):
    def __init__(self, py_value):
        GObjectModule.Value.__init__(self)
        self.init(GObject.TYPE_PYOBJECT)
        if py_value is not None:
            self.set_boxed(py_value)


class GEnum(GObject.Value):
    def __init__(self, py_value, gtype):
        GObjectModule.Value.__init__(self)
        self.init(gtype)
        self.set_enum(py_value)


class GPangoStyle(GEnum):
    def __init__(self, py_value):
        GEnum.__init__(self, py_value, Pango.Style)


class GPangoWeight(GEnum):
    def __init__(self, py_value):
        GEnum.__init__(self, py_value, Pango.Weight)


class RowFactory(object):
    def __init__(self, tree):
        self.tree = tree
        self.n_columns = tree.get_n_columns()
        self.columns_type = {
            n: tree.get_column_type(n)
            for n in range(self.n_columns)
        }
        self.py_2_gi = {
            GObject.TYPE_STRING: GString,
            GObject.TYPE_BOOLEAN: GBool,
            GObject.TYPE_PYOBJECT: GPyObject,
            TYPE_PANGO_STYLE: GPangoStyle,
            TYPE_PANGO_WEIGHT: GPangoWeight,
            TYPE_GDK_RGBA: lambda v: v
        }

    def make(self, row):
        result = {}
        for col_num, col_type in self.columns_type.items():
            val = row.get(col_num, None)
            if val is not None and col_type in self.py_2_gi \
                or col_type == GObject.TYPE_PYOBJECT and val is None:
                result[col_num] = self.py_2_gi[col_type](val)
        return result

    def append(self, parent, row_info):
        columns = tuple(row_info.keys())
        row = tuple(row_info.values())
        return self.tree.insert_with_values(parent, -1, columns, row)


if __name__ == '__main__':
    import sys
    for _ in range(100000):
        if 'gvalue' in sys.argv:
            GObject.Value(GObject.TYPE_STRING, "OLA")
        elif 'GString' in sys.argv:
            GString("OLA")
        else:
            str("OLA")