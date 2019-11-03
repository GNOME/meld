
from unittest import mock

import pytest
from gi.repository import GtkSource


@pytest.mark.parametrize("text, newline, expected_text", [
    # For the following tests, newlines and text match
    # Basic CRLF tests
    ("ree\r\neee", GtkSource.NewlineType.CR_LF, 'ree'),
    ("ree\r\neee\r\n", GtkSource.NewlineType.CR_LF, 'ree\r\neee'),
    # Basic CR tests
    ("ree\neee", GtkSource.NewlineType.CR, 'ree'),
    ("ree\neee\n", GtkSource.NewlineType.CR, 'ree\neee'),
    # Basic LF tests
    ("ree\reee", GtkSource.NewlineType.LF, 'ree'),
    ("ree\reee\r", GtkSource.NewlineType.LF, 'ree\reee'),

    # Mismatched newline and text
    ("ree\r\neee", GtkSource.NewlineType.CR, 'ree'),

    # Mismatched newline types within text
    ("ree\r\neee\n", GtkSource.NewlineType.CR_LF, 'ree\r\neee'),
    ("ree\r\neee\nqqq", GtkSource.NewlineType.CR_LF, 'ree\r\neee'),
    ("ree\r\neee\nqqq\r\n", GtkSource.NewlineType.CR_LF, 'ree\r\neee\nqqq'),
])
def test_delete_last_line_crlf(text, newline, expected_text):
    import meld.meldbuffer
    from meld.filediff import FileDiff
    from meld.matchers.myers import DiffChunk

    filediff = mock.Mock(FileDiff)

    with mock.patch('meld.meldbuffer.bind_settings', mock.DEFAULT):
        meldbuffer = meld.meldbuffer.MeldBuffer()
        meldbuffer.set_text(text)

    def make_last_line_chunk(buf):
        end = buf.get_line_count()
        last = end - 1
        return DiffChunk('delete', last, end, last, end)

    start, end = meldbuffer.get_bounds()
    buf_text = meldbuffer.get_text(start, end, False)
    print(repr(buf_text))

    with mock.patch.object(
            meldbuffer.data.sourcefile,
            'get_newline_type', return_value=newline):
        filediff.textbuffer = [meldbuffer]
        filediff.textview = [mock.Mock()]
        FileDiff.delete_chunk(filediff, 0, make_last_line_chunk(meldbuffer))

    start, end = meldbuffer.get_bounds()
    buf_text = meldbuffer.get_text(start, end, False)
    print(repr(buf_text))
    assert buf_text == expected_text
