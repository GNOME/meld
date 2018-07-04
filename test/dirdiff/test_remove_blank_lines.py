import pytest
from meld.dirdiff import remove_blank_lines, NEWLINE_RE

@pytest.mark.parametrize('txt, expected', [
    # blank to be equal blank
    (b'', b''),
    # one line with spaces
    (b' ', b' '),
    # two lines empty
    (b'\n', b''),
    (b'\n ', b' '),
    (b' \n', b' '),
    (b' \n ', b' \n '),
    # tree lines empty
    (b'\n\n', b''),
    (b'\n\n ', b' '),
    (b'\n \n', b' '),
    (b'\n \n ', b' \n '),
    (b' \n \n ', b' \n \n '),
    # one line with space and content
    (b' content', b' content'),
    # empty line between content
    (b'content\n\ncontent', b'content\ncontent'),
    # multiple leading and trailing newlines
    (b'\n\ncontent\ncontent\n\n\n', b'content\ncontent'),
])
def test_remove_blank_lines(txt, expected):
    result = remove_blank_lines(txt)
    assert result == expected


@pytest.mark.parametrize('txt, expected', [
    # blank to be equal blank
    (b'', b''),
    # one line with spaces
    (b' ', b' '),
    # two lines
    (b'\n', b'\n'),
    (b'\r', b'\n'),
    (b'\v', b'\n'),
    (b'\f', b'\n'),
    (b'\x0b', b'\n'),
    (b'\x0c', b'\n'),
    (b'\x1c', b'\n'),
    (b'\x1d', b'\n'),
    (b'\x1e', b'\n'),
    (b'\x85', b'\n'),
    # (b'\r\n', b'\n'),
    # tree lines
    (b'\n\x0c', b'\n\n'),
    (b'\n\x0b ', b'\n\n '),
    (b'\n \f ', b'\n \n '),
    (b'\n \v ', b'\n \n '),
    (b' \n \r\n ', b' \n \n '),
    # all new line separetos know by slitlines
    (b'\n\r\v\x0b\f\x0c\x1c\x1d\x1e\x85', b'\n\n\n\n\n\n\n\n\n\n'),
])
def test_newline_re(txt, expected):
    result = NEWLINE_RE.sub(b'\n', txt)
    assert result == expected
