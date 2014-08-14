#! /usr/bin/env python3

import collections
import datetime
import os
import subprocess

from jinja2 import Environment, Template

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
{% for translator in translator_langs|sort %}
   * {{ translator }} ({{translator_langs[translator]|sort|join(', ')}})
{%- endfor %}

"""

EMAIL_TEMPLATE = """
{{ app|title }} {{version}} has been released, and is now available at:
  http://download.gnome.org/sources/meld/{{ version|minor_version }}/{{ app }}-{{ version }}.tar.xz


Features
--------
{% for feature in features %}
 {{ feature }}
{%- endfor %}


Fixes
-----
{% for fix in fixes %}
 {{ fix }}
{%- endfor %}


Translations
------------
{% for translator in translators %}
 {{ translator }}
{%- endfor %}


What is Meld?
-------------

Meld is a visual diff and merge tool. It lets you compare two or three files,
and updates the comparisons while you edit them in-place. You can also compare
folders, launching comparisons of individual files as desired. Last but by no
means least, Meld lets you work with your current changes in a wide variety of
version control systems, including Git, Bazaar, Mercurial and Subversion.
"""


MARKDOWN_TEMPLATE = """
<!--
{{ [date, app, version]|join(' ') }}
{{ '=' * [date, app, version]|join(' ')|length }}
-->

Features
--------
{% for feature in features %}
{{ feature }}
{%- endfor %}

Fixes
-----
{% for fix in fixes %}
{{ fix }}
{%- endfor %}

Translations
------------
{% for translator in translators %}
{{ translator }}
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


def get_last_news_entry():
    cmd = ['git', 'log', '--pretty=format:', '-p', '-1', 'NEWS']
    lines = subprocess.check_output(cmd).strip().decode('utf-8').splitlines()
    lines = [l[1:] for l in lines if (l and l[0] in ('+', '-')) and
             (len(l) < 2 or l[1] not in ('+', '-'))]
    return "\n".join(lines)


def parse_news_entry(news):
    features, fixes, translators = [], [], []
    section = None
    sections = {
        'Features': features,
        'Fixes': fixes,
        'Translations': translators,
    }
    for line in news.splitlines():
        if line.strip(' :') in sections:
            section = line.strip(' :')
            continue
        if not section or not line.strip():
            continue
        sections[section].append(line)

    def reformat(section):
        def space_prefix(s):
            for i in range(1, len(s)):
                if not s[:i].isspace():
                    break
            return i - 1

        indent = min(space_prefix(l) for l in section)
        return [l[indent:] for l in section]

    return reformat(features), reformat(fixes), reformat(translators)


def make_env():

    def minor_version(version):
        return '.'.join(version.split('.')[:2])

    jinja_env = Environment()
    jinja_env.filters['minor_version'] = minor_version
    return jinja_env


def get_tokens():
    news = get_last_news_entry()
    features, fixes, translators = parse_news_entry(news)
    return {
        'date': datetime.date.today().isoformat(),
        'app': meld.conf.__package__,
        'version': meld.conf.__version__,
        'translator_langs': get_translator_langs(),
        'features': features,
        'fixes': fixes,
        'translators': translators,
        'commits': get_non_translation_commits(),
    }


def format_news(jinja_env, tokens):
    template = jinja_env.from_string(NEWS_TEMPLATE)
    return(template.render(tokens))


def format_email(jinja_env, tokens):
    template = jinja_env.from_string(EMAIL_TEMPLATE)
    return(template.render(tokens))


def format_markdown(jinja_env, tokens):
    template = jinja_env.from_string(MARKDOWN_TEMPLATE)
    return(template.render(tokens))


if __name__ == '__main__':
    tokens = get_tokens()
    jinja_env = make_env()

    print(format_news(jinja_env, tokens))
    print(format_email(jinja_env, tokens))
    print(format_markdown(jinja_env, tokens))
