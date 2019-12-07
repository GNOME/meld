# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2011-2016 Kai Willadsen <kai.willadsen@gmail.com>
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

from gi.repository import Gtk


def tree_path_as_tuple(path):
    """Get the path indices as a tuple

    This helper only exists because we often want to use tree paths
    as set members or dictionary keys, and this is a convenient option.
    """
    return tuple(path.get_indices())


def tree_path_prev(path):
    if not path or path[-1] == 0:
        return None
    return path[:-1] + [path[-1] - 1]


def tree_path_up(path):
    if not path:
        return None
    return path[:-1]


def valid_path(model, path):
    try:
        model.get_iter(path)
        return True
    except ValueError:
        return False


def refocus_deleted_path(model, path):
    # Since the passed path has been deleted, either the path is now a
    # valid successor, or there are no successors. If valid, return it.
    # If not, and the path has a predecessor sibling (immediate or
    # otherwise), then return that. If there are no siblings, traverse
    # parents until we get a valid path, and return that.

    if valid_path(model, path):
        return path

    new_path = tree_path_prev(path)
    while new_path:
        if valid_path(model, new_path):
            return new_path
        new_path = tree_path_prev(new_path)

    new_path = tree_path_up(path)
    while new_path:
        if valid_path(model, new_path):
            return new_path
        new_path = tree_path_up(new_path)


class SearchableTreeStore(Gtk.TreeStore):

    def inorder_search_down(self, it):
        while it:
            child = self.iter_children(it)
            if child:
                it = child
            else:
                next_it = self.iter_next(it)
                if next_it:
                    it = next_it
                else:
                    while True:
                        it = self.iter_parent(it)
                        if not it:
                            return
                        next_it = self.iter_next(it)
                        if next_it:
                            it = next_it
                            break
            yield it

    def inorder_search_up(self, it):
        while it:
            path = self.get_path(it)
            if path[-1]:
                path = path[:-1] + [path[-1] - 1]
                it = self.get_iter(path)
                while 1:
                    nc = self.iter_n_children(it)
                    if nc:
                        it = self.iter_nth_child(it, nc - 1)
                    else:
                        break
            else:
                up = self.iter_parent(it)
                if up:
                    it = up
                else:
                    return
            yield it

    def get_previous_next_paths(self, path, match_func):
        prev_path, next_path = None, None
        try:
            start_iter = self.get_iter(path)
        except ValueError:
            # Invalid tree path
            return None, None

        for it in self.inorder_search_up(start_iter):
            if match_func(it):
                prev_path = self.get_path(it)
                break

        for it in self.inorder_search_down(start_iter):
            if match_func(it):
                next_path = self.get_path(it)
                break

        return prev_path, next_path
