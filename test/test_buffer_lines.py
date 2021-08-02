
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
10
""")


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
