import pytest
from meld.dirdiff import remove_blank_lines


@pytest.mark.parametrize('txt, expected', [
    # blank to be equal blank
    (b'', b''),
    # one line with spaces
    (b' ', b''),
    # two lines empty
    (b'\n', b''),
    (b'\r\n', b''),
    (b'\r', b''),
    (b'\f', b''),
    (b'\n ', b''),
    (b' \n', b''),
    (b' \n ', b''),
    # tree lines empty
    (b'\n\n', b''),
    (b'\n\n ', b''),
    (b'\n \n', b''),
    (b'\n \n ', b''),
    (b' \n \n ', b''),
    # one line with space and char
    (b' c', b' c'),
    # empty line between content
    (b'c\n \nc', b'c\nc'),
    # multiple leading and trailing newlines
    (b'\n\ncontent\ncontent\n\n\n', b'content\ncontent\n'),
])
def test_blank_re(txt, expected):
    result = remove_blank_lines(txt)
    assert result == expected
