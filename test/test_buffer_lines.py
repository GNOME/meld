
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
def test_filter_text(line_start, line_end, expected_text):

    with mock.patch('meld.meldbuffer.bind_settings', mock.DEFAULT):
        buf = MeldBuffer()
        buf.set_text(text)

        buffer_lines = BufferLines(buf)
        assert buffer_lines[line_start:line_end] == expected_text
