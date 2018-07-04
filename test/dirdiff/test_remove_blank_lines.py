import pytest
from meld.dirdiff import remove_blank_lines


@pytest.mark.parametrize('txt, expected', [
    # blank to be equal blank
    (b'', b''),
    # one line with spaces
    (b' ', b' '),
    # two lines empty
    (b'\n', b''),
    (b'\r\n', b''),
    (b'\r', b''),
    (b'\f', b''),
    (b'\x85', b''),
    (b'\x1e ', b' '),
    (b' \x1d', b' '),
    (b' \x1c ', b' \n '),
    # tree lines empty
    (b'\n\x0c', b''),
    (b'\n\x0b ', b' '),
    (b'\n \f', b' '),
    (b'\n \v ', b' \n '),
    (b' \n \r\n ', b' \n \n '),
    # one line with space and char
    (b' content', b' content'),
    # empty line between content
    (b'content\n \rcontent', b'content\n \ncontent'),
    # multiple leading and trailing newlines
    (b'\n\ncontent\ncontent\n\n\n', b'content\ncontent'),
    # all new line separetos know by slitlines
    (b'\n\r\v\x0b\f\x0c\x1c\x1d\x1e\x85', b''),
    (b'content\n\r\v\f\x1c\x1d\x1e\x85content', b'content\ncontent'),
])
def test_blank_re(txt, expected):
    result = remove_blank_lines(txt)
    assert result == expected
