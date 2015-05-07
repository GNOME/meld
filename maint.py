#! /usr/bin/env python3

import collections
import datetime
import os
import re
import subprocess

import click
from jinja2 import Environment

import meld.conf

PO_DIR = "po"
HELP_DIR = "help"
RELEASE_BRANCH_RE = r'%s-\d+-\d+' % meld.conf.__package__
VERSION_RE = r'__version__\s*=\s*"(?P<version>.*)"'
UPLOAD_SERVER = 'master.gnome.org'

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
{%- if features %}


Features
--------
{% for feature in features %}
 {{ feature }}
{%- endfor %}
{%- endif %}


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
{%- if features %}

Features
--------
{% for feature in features %}
{{ feature }}
{%- endfor %}
{%- endif %}

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
        if not section:
            return section

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


def render_template(template):
    tokens = get_tokens()
    jinja_env = make_env()
    template = jinja_env.from_string(template)
    return(template.render(tokens))


def call_with_output(
        cmd, stdin_text=None, echo_stdout=True, abort_on_fail=True,
        timeout=10):
    PIPE = subprocess.PIPE
    with subprocess.Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE) as proc:
        stdout, stderr = proc.communicate(stdin_text, timeout=timeout)
    if stdout and echo_stdout:
        click.echo('\n' + stdout.decode('utf-8'))
    if stderr or proc.returncode:
        click.secho('\n' + stderr.decode('utf-8'), fg='red')
    if abort_on_fail and proc.returncode:
        raise click.Abort()
    return proc.returncode


def check_release_branch():
    cmd = ['git', 'rev-parse', '--abbrev-ref', 'HEAD']
    branch = subprocess.check_output(cmd).strip().decode('utf-8')
    if branch != 'master' and not re.match(RELEASE_BRANCH_RE, branch):
        click.echo(
            '\nBranch "%s" doesn\'t appear to be a release branch.\n' % branch)
        click.confirm('Are you sure you wish to continue?', abort=True)
    return branch


def pull():
    check_release_branch()
    cmd = ['git', 'pull', '--rebase']
    call_with_output(cmd, timeout=None)


def commit(message=None):
    cmd = ['git', 'diff', 'HEAD']
    call_with_output(cmd, echo_stdout=True)
    confirm = click.confirm('\nCommit this change?', default=True)
    if not confirm:
        return

    cmd = ['git', 'commit', '-a']
    if message:
        cmd.append('-m ' + message)
    call_with_output(cmd, timeout=None)


def push():
    branch = check_release_branch()
    cmd = ['git', 'log', 'origin/%s..%s' % (branch, branch)]
    call_with_output(cmd, echo_stdout=True)

    confirm = click.confirm('\nPush these commits?', default=True)
    if not confirm:
        return

    cmd = ['git', 'push']
    call_with_output(cmd, echo_stdout=True)


@click.group()
def cli():
    pass

@cli.command()
def test():
    cmd = ['python', '-m', 'unittest', 'discover']
    call_with_output(cmd, echo_stdout=True)    

@cli.command()
def news():
    rendered = render_template(NEWS_TEMPLATE)
    with open('NEWS', 'r') as f:
        current_news = f.read()

    new_news = rendered + current_news
    with open('NEWS', 'w') as f:
        f.write(new_news)

    message = click.edit(filename='NEWS')
    return message


def write_somewhere(filename, output):
    if filename and os.path.exists(filename):
        overwrite = click.confirm(
            'File "%s" already exists. Overwrite?' % filename, abort=True)
        if not overwrite:
            raise click.Abort()
    if filename:
        with open(filename, 'w') as f:
            f.write(output)
        click.echo('Wrote %s' % filename)
    else:
        click.echo(output)


@cli.command()
@click.argument('filename', type=click.Path(), default=None, required=False)
def email(filename):
    write_somewhere(filename, render_template(EMAIL_TEMPLATE))


@cli.command()
@click.argument('filename', type=click.Path(), default=None, required=False)
def markdown(filename):
    write_somewhere(filename, render_template(MARKDOWN_TEMPLATE))


@cli.command()
def dist():
    archive = '%s-%s.tar.bz2' % (meld.conf.__package__, meld.conf.__version__)
    dist_archive_path = os.path.abspath(os.path.join('dist', archive))
    if os.path.exists(dist_archive_path):
        click.echo('Replacing %s...' % dist_archive_path)
    cmd = ['python', 'setup.py', 'sdist', '--formats=bztar']
    call_with_output(cmd, echo_stdout=False)
    if not os.path.exists(dist_archive_path):
        click.echo('Failed to create archive file %s' % dist_archive_path)
        raise click.Abort()
    return dist_archive_path


@cli.command()
def tag():
    last_release = get_last_release_tag()
    click.echo('\nLast release tag was: ', nl=False)
    click.secho(last_release, fg='green', bold=True)
    click.echo('New release tag will be: ', nl=False)
    click.secho(meld.conf.__version__, fg='green', bold=True)
    click.confirm('\nTag this release?', default=True, abort=True)

    news_text = get_last_news_entry().encode('utf-8')
    # FIXME: Should be signing tags
    cmd = ['git', 'tag', '-a', '--file=-', meld.conf.__version__]
    call_with_output(cmd, news_text)
    click.echo('Tagged %s' % meld.conf.__version__)

    cmd = ['git', 'show', '-s', meld.conf.__version__]
    call_with_output(cmd, echo_stdout=True)
    confirm = click.confirm('\nPush this tag?', default=True)
    if not confirm:
        return

    cmd = ['git', 'push', 'origin', meld.conf.__version__]
    call_with_output(cmd, echo_stdout=True)


@cli.command()
@click.argument('path', type=click.Path(exists=True))
def upload(path):
    confirm = click.confirm(
        '\nUpload %s to %s?' % (path, UPLOAD_SERVER), default=True,
        abort=False)
    if not confirm:
        return
    cmd = ['scp', path, UPLOAD_SERVER + ':']
    call_with_output(cmd, timeout=120)


@cli.command()
def version_bump():
    with open(meld.conf.__file__) as f:
        conf_data = f.read().splitlines()

    for i, line in enumerate(conf_data):
        if line.startswith('__version__'):
            match = re.match(VERSION_RE, line)
            version = match.group('version')
            if version != meld.conf.__version__:
                continue
            version_line = i
            break
    else:
        click.echo('Couldn\'t determine version from %s' % meld.conf.__file__)
        raise click.Abort()

    click.echo('Current version is: %s' % meld.conf.__version__)
    default_version = meld.conf.__version__.split('.')
    default_version[-1] = str(int(default_version[-1]) + 1)
    default_version = '.'.join(default_version)
    new_version = click.prompt('Enter new version', default=default_version)

    conf_data[version_line] = '__version__ = "%s"' % new_version
    with open(meld.conf.__file__, 'w') as f:
        f.write('\n'.join(conf_data) + '\n')


@cli.command()
@click.pass_context
def make_release(ctx):
    pull()
    ctx.forward(news)
    commit(message='Update NEWS')
    push()
    archive_path = ctx.forward(dist)
    ctx.forward(tag)
    ctx.forward(upload, path=archive_path)
    file_prefix = '%s-%s' % (meld.conf.__package__, meld.conf.__version__)
    ctx.forward(email, filename=file_prefix + '-email')
    ctx.forward(markdown, filename=file_prefix + '.md')
    ctx.forward(version_bump)
    commit(message='Post-release version bump')
    push()

    # TODO: ssh in and run ftpadmin install
    click.echo('\nNow run:')
    click.echo('ssh %s' % UPLOAD_SERVER)
    click.echo('ftpadmin install %s' % os.path.basename(archive_path))


if __name__ == '__main__':
    # FIXME: Should include sanity check that we're at the top level of the
    # project
    cli()
