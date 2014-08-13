#! /usr/bin/env python3

import collections
import datetime
import os
import subprocess

from jinja2 import Template

import meld.conf

PO_DIR = "po"
HELP_DIR = "help"

NEWS_TEMPLATE = """
{{ [date, app, version]|join(' ') }}
{{ '=' * [date, app, version]|join(' ')|length }}

  Features:


  Fixes:
{% for commit in commits%}
   * {{ commit }}
{%- endfor %}

  Translations:
{% for translator in translators|sort %}
   * {{ translator }} ({{translators[translator]|sort|join(', ')}})
{%- endfor %}

"""


def get_last_release_tag():
    cmd = ['git', 'describe', '--abbrev=0', '--tags']
    tag_name = subprocess.check_output(cmd).strip().decode('utf-8')
    try:
        version = [int(v) for v in tag_name.split('.')]
        if len(version) != 3:
            raise ValueError()
    except ValueError:
        raise ValueError("Couldn't parse tag name %s" % tag_name)
    return tag_name


def get_translation_commits(folder):
    last_release = get_last_release_tag()
    revspec = "%s..HEAD" % last_release
    cmd = ['git', 'log', '--pretty=format:%an', '--name-only', revspec,
           '--', folder]
    name_files = subprocess.check_output(cmd).strip().decode('utf-8')
    if not name_files:
        return []
    commits = name_files.split('\n\n')
    commits = [(c.split('\n')[0], c.split('\n')[1:]) for c in commits]
    return commits


def get_translator_langs(folders=[PO_DIR, HELP_DIR]):

    def get_lang(path):
        filename = os.path.basename(path)
        if not filename.endswith('.po'):
            return None
        return filename[:-3]

    translation_commits = []
    for folder in folders:
        translation_commits.extend(get_translation_commits(folder))

    author_map = collections.defaultdict(set)
    for author, langs in translation_commits:
        langs = [get_lang(lang) for lang in langs if get_lang(lang)]
        author_map[author] |= set(langs)

    return author_map


def get_non_translation_commits():
    last_release = get_last_release_tag()
    revspec = "%s..HEAD" % last_release
    # FIXME: Use the Git 1.9 spec to negate logging translation commits
    cmd = ['git', 'log', '--pretty=format:%s (%an)', revspec]
    commits = subprocess.check_output(cmd).strip().splitlines()
    return [c.decode('utf-8') for c in commits]


def format_news():

    tokens = {
        'date': datetime.date.today().isoformat(),
        'app': meld.conf.__package__,
        'version': meld.conf.__version__,
        'translators': get_translator_langs(),
        'commits': get_non_translation_commits(),
    }

    template = Template(NEWS_TEMPLATE)
    return(template.render(tokens))


if __name__ == '__main__':
    print(format_news())
