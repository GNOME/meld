
from unittest import mock

import pytest

from meld.meldbuffer import BufferLines, MeldBuffer

text = ("""0
1
2
3
4
5
6
7
8
9
10""")


@pytest.fixture(scope='module', autouse=True)
def mock_bind_settings():
    with mock.patch('meld.meldbuffer.bind_settings', mock.DEFAULT):
        yield


@pytest.fixture
def buffer_setup():
    buf = MeldBuffer()
    buf.set_text(text)
    buffer_lines = BufferLines(buf)
    yield buf, buffer_lines


@pytest.mark.parametrize("line_start, line_end, expected_text", [
    (0, 1, ["0"],),
    (0, 2, ["0", "1"],),
    # zero-sized slice
    (9, 9, [],),
    (9, 10, ["9"],),
    (9, 11, ["9", "10"],),
    # Past the end of the buffer
    (9, 12, ["9", "10"],),
    # Waaaay past the end of the buffer
    (9, 9999, ["9", "10"],),
    # And sidling towards past-the-end start indices
    (10, 12, ["10"],),
    (11, 12, [],),
])
def test_meld_buffer_slicing(
        line_start, line_end, expected_text, buffer_setup):

    buffer, buffer_lines = buffer_setup
    assert buffer_lines[line_start:line_end] == expected_text


def test_meld_buffer_index_out_of_range(buffer_setup):

    buffer, buffer_lines = buffer_setup
    with pytest.raises(IndexError):
        buffer_lines[11]


def test_meld_buffer_cached_contents(buffer_setup):

    buffer, buffer_lines = buffer_setup
    text_lines = text.splitlines()
    assert len(buffer_lines.lines) == len(buffer_lines) == len(text_lines)

    # Check that without access, we have no cached contents
    assert buffer_lines.lines == [None] * len(text_lines)

    # Access the lines so that they're cached
    buffer_lines[:]

    # Note that this only happens to be true for our simple text; if
    # it were true in general, we wouldn't need the complexities of the
    # BufferLines class.
    assert buffer_lines.lines == text_lines


def test_meld_buffer_insert_text(buffer_setup):

    buffer, buffer_lines = buffer_setup

    # Access the lines so that they're cached
    buffer_lines[:]

    assert buffer_lines.lines[4:8] == ["4", "5", "6", "7"]

    # Delete from the start of line 5 to the start of line 7,
    # invalidating line 7 but leaving its contents intact.
    buffer.insert(
        buffer.get_iter_at_line(5),
        "hey\nthings",
    )
    assert buffer_lines.lines[4:8] == ["4", None, None, "6"]

    assert buffer_lines[5:7] == ["hey", "things5"]
    assert buffer_lines.lines[4:8] == ["4", "hey", "things5", "6"]


def test_meld_buffer_delete_range(buffer_setup):

    buffer, buffer_lines = buffer_setup

    # Access the lines so that they're cached
    buffer_lines[:]

    assert buffer_lines.lines[4:8] == ["4", "5", "6", "7"]

    # Delete from the start of line 5 to the start of line 7,
    # invalidating line 7 but leaving its contents intact.
    buffer.delete(
        buffer.get_iter_at_line(5),
        buffer.get_iter_at_line(7),
    )
    assert buffer_lines.lines[4:7] == ["4", None, "8"]

    assert buffer_lines[5] == "7"
    assert buffer_lines.lines[4:7] == ["4", "7", "8"]


def test_meld_buffer_cache_debug(caplog, buffer_setup):

    buffer, buffer_lines = buffer_setup
    buffer_lines = BufferLines(buffer, cache_debug=True)

    # Invalidate our line cache...
    buffer_lines.lines.append("invalid")

    # ...and check that insertion/deletion logs an error
    buffer.insert(
        buffer.get_iter_at_line(5),
        "hey",
    )
    assert len(caplog.records) == 1
    assert caplog.records[0].msg.startswith("Cache line count does not match")
    caplog.clear()

    buffer.delete(
        buffer.get_iter_at_line(5),
        buffer.get_iter_at_line(7),
    )
    assert len(caplog.records) == 1
    assert caplog.records[0].msg.startswith("Cache line count does not match")
