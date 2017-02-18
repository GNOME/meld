
from unittest import mock

import pytest

import meld.gutterrendererchunk
from meld.gutterrendererchunk import GutterRendererChunkAction
from meld.const import MODE_REPLACE, MODE_DELETE, MODE_INSERT
from meld.matchers.myers import DiffChunk


def make_chunk(chunk_type):
    return DiffChunk(chunk_type, 0, 1, 0, 1)


@pytest.mark.parametrize("mode, editable, chunk, expected_action", [
    # Replace mode with replace chunks
    (MODE_REPLACE, (True, True), make_chunk('replace'), MODE_REPLACE),
    (MODE_REPLACE, (True, False), make_chunk('replace'), MODE_DELETE),
    (MODE_REPLACE, (False, True), make_chunk('replace'), MODE_REPLACE),
    (MODE_REPLACE, (False, False), make_chunk('replace'), None),
    # Replace mode with delete chunks
    (MODE_REPLACE, (True, True), make_chunk('delete'), MODE_REPLACE),
    (MODE_REPLACE, (True, False), make_chunk('delete'), MODE_DELETE),
    (MODE_REPLACE, (False, True), make_chunk('delete'), MODE_REPLACE),
    (MODE_REPLACE, (False, False), make_chunk('delete'), None),
    # Delete mode makes a slightly weird choice to remove non-delete
    # actions while in delete mode; insert mode makes the opposite
    # choice
    #
    # Delete mode with replace chunks
    (MODE_DELETE, (True, True), make_chunk('replace'), MODE_DELETE),
    (MODE_DELETE, (True, False), make_chunk('replace'), MODE_DELETE),
    (MODE_DELETE, (False, True), make_chunk('replace'), None),
    (MODE_DELETE, (False, False), make_chunk('replace'), None),
    # Delete mode with delete chunks
    (MODE_DELETE, (True, True), make_chunk('delete'), MODE_DELETE),
    (MODE_DELETE, (True, False), make_chunk('delete'), MODE_DELETE),
    (MODE_DELETE, (False, True), make_chunk('delete'), None),
    (MODE_DELETE, (False, False), make_chunk('delete'), None),
    # Insert mode with replace chunks
    (MODE_INSERT, (True, True), make_chunk('replace'), MODE_INSERT),
    (MODE_INSERT, (True, False), make_chunk('replace'), MODE_DELETE),
    (MODE_INSERT, (False, True), make_chunk('replace'), MODE_INSERT),
    (MODE_INSERT, (False, False), make_chunk('replace'), None),
    # Insert mode with delete chunks
    (MODE_INSERT, (True, True), make_chunk('delete'), MODE_REPLACE),
    (MODE_INSERT, (True, False), make_chunk('delete'), MODE_DELETE),
    (MODE_INSERT, (False, True), make_chunk('delete'), MODE_REPLACE),
    (MODE_INSERT, (False, False), make_chunk('delete'), None),
    # We should never have insert chunks here
    (MODE_REPLACE, (True, True), make_chunk('insert'), None),
    (MODE_REPLACE, (True, False), make_chunk('insert'), None),
    (MODE_REPLACE, (False, True), make_chunk('insert'), None),
    (MODE_REPLACE, (False, False), make_chunk('insert'), None),

    # TODO: Add tests for conflict chunks
])
def test_classify_change_actions(mode, editable, chunk, expected_action):
    filediff = mock.MagicMock()
    meld.gutterrendererchunk.meldsettings = mock.MagicMock(style_scheme=None)
    GutterRendererChunkAction.on_setting_changed = mock.MagicMock()
    renderer = GutterRendererChunkAction(
        0, 1, mock.MagicMock(), filediff, None)

    renderer.mode = mode
    renderer.views_editable = editable
    action = renderer._classify_change_actions(chunk)

    assert action == expected_action
