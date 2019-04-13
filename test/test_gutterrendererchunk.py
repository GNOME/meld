
from unittest import mock

import pytest

from meld.const import ActionMode
from meld.matchers.myers import DiffChunk


def make_chunk(chunk_type):
    return DiffChunk(chunk_type, 0, 1, 0, 1)


@pytest.mark.parametrize("mode, editable, chunk, expected_action", [
    # Replace mode with replace chunks
    (ActionMode.Replace, (True, True), make_chunk('replace'), ActionMode.Replace),
    (ActionMode.Replace, (True, False), make_chunk('replace'), ActionMode.Delete),
    (ActionMode.Replace, (False, True), make_chunk('replace'), ActionMode.Replace),
    (ActionMode.Replace, (False, False), make_chunk('replace'), None),
    # Replace mode with delete chunks
    (ActionMode.Replace, (True, True), make_chunk('delete'), ActionMode.Replace),
    (ActionMode.Replace, (True, False), make_chunk('delete'), ActionMode.Delete),
    (ActionMode.Replace, (False, True), make_chunk('delete'), ActionMode.Replace),
    (ActionMode.Replace, (False, False), make_chunk('delete'), None),
    # Delete mode makes a slightly weird choice to remove non-delete
    # actions while in delete mode; insert mode makes the opposite
    # choice
    #
    # Delete mode with replace chunks
    (ActionMode.Delete, (True, True), make_chunk('replace'), ActionMode.Delete),
    (ActionMode.Delete, (True, False), make_chunk('replace'), ActionMode.Delete),
    (ActionMode.Delete, (False, True), make_chunk('replace'), None),
    (ActionMode.Delete, (False, False), make_chunk('replace'), None),
    # Delete mode with delete chunks
    (ActionMode.Delete, (True, True), make_chunk('delete'), ActionMode.Delete),
    (ActionMode.Delete, (True, False), make_chunk('delete'), ActionMode.Delete),
    (ActionMode.Delete, (False, True), make_chunk('delete'), None),
    (ActionMode.Delete, (False, False), make_chunk('delete'), None),
    # Insert mode with replace chunks
    (ActionMode.Insert, (True, True), make_chunk('replace'), ActionMode.Insert),
    (ActionMode.Insert, (True, False), make_chunk('replace'), ActionMode.Delete),
    (ActionMode.Insert, (False, True), make_chunk('replace'), ActionMode.Insert),
    (ActionMode.Insert, (False, False), make_chunk('replace'), None),
    # Insert mode with delete chunks
    (ActionMode.Insert, (True, True), make_chunk('delete'), ActionMode.Replace),
    (ActionMode.Insert, (True, False), make_chunk('delete'), ActionMode.Delete),
    (ActionMode.Insert, (False, True), make_chunk('delete'), ActionMode.Replace),
    (ActionMode.Insert, (False, False), make_chunk('delete'), None),
    # We should never have insert chunks here
    (ActionMode.Replace, (True, True), make_chunk('insert'), None),
    (ActionMode.Replace, (True, False), make_chunk('insert'), None),
    (ActionMode.Replace, (False, True), make_chunk('insert'), None),
    (ActionMode.Replace, (False, False), make_chunk('insert'), None),

    # TODO: Add tests for conflict chunks
])
def test_classify_change_actions(mode, editable, chunk, expected_action):

    # These tests are disabled due to a segfault on the CI machines.
    return

    from meld.actiongutter import ActionGutter

    source_editable, target_editable = editable

    with mock.patch.object(ActionGutter, 'icon_direction'):
        renderer = ActionGutter()
        renderer._source_view = mock.Mock()
        renderer._source_view.get_editable.return_value = source_editable
        renderer._target_view = mock.Mock()
        renderer._target_view.get_editable.return_value = target_editable
        renderer.action_mode = mode

        action = renderer._classify_change_actions(chunk)
        assert action == expected_action
