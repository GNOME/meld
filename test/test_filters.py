
import pytest


@pytest.mark.parametrize("patterns,filename,expected_match", [
    ([r'*.csv'], 'foo.csv', True),
    ([r'*.cvs'], 'foo.csv', False),
    ([r'*.csv *.xml'], 'foo.csv', True),
    ([r'*.csv *.xml'], 'foo.xml', True),
    ([r'*.csv', r'*.xml'], 'foo.csv', True),
    ([r'*.csv', r'*.xml'], 'foo.xml', True),
    ([r'*.csv', r'*.xml'], 'dumbtest', False),
    ([r'thing*csv'], 'thingcsv', True),
    ([r'thing*csv'], 'thingwhatevercsv', True),
    ([r'thing*csv'], 'csvthing', False),
])
def test_file_filters(patterns, filename, expected_match):
    from meld.filters import FilterEntry

    filters = [
        FilterEntry.new_from_gsetting(("name", True, p), FilterEntry.SHELL)
        for p in patterns
    ]

    # All of the dirdiff logic is "does this match any filter", so
    # that's what we test here, even if it looks a bit weird.
    match = any(f.filter.match(filename) for f in filters)
    assert match == expected_match


@pytest.mark.parametrize("pattern", [
    r'*.foo*',  # Trailing wildcard
    r'\xfoo',  # Invalid escape
])
def test_bad_regex_compilation(pattern):
    from meld.filters import FilterEntry

    f = FilterEntry.new_from_gsetting(
        ("name", True, pattern), FilterEntry.REGEX)
    assert f.filter is None
