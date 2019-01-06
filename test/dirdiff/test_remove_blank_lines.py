import pytest


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
    (b'\n\n\ncontent\n\n\ncontent\n\n\n', b'content\ncontent'),
])
def test_remove_blank_lines(txt, expected):
    from meld.dirdiff import remove_blank_lines

    result = remove_blank_lines(txt)
    assert result == expected
