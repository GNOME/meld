#! /usr/bin/python3

import glob
import os
import subprocess
import sys

from bs4 import BeautifulSoup

JEKYLL_HEADER = """---
layout: help
title: Meld - Help
---
"""

SCSS_HEADER = """
#help-content {
  border-left: solid 1px #e0e0df;
  border-right: solid 1px #e0e0df;
  background-color: #ffffff;
}

#help-content div.body {
  border: none !important; }

#help-content div.headbar {
  margin: 10px !important;
}

#help-content div.footbar {
  margin: 10px !important;
}

#help-content {

.title {
  line-height: 1em;
}

h1 {
  font-family: sans-serif;
  font-weight: bold;
  text-shadow: none;
  color: black;
}

h2 {
  font-family: sans-serif;
  text-shadow: none;
  color: black;
}
"""

SCSS_FOOTER = """
}
"""


def munge_html(filename):
    if not os.path.exists(filename):
        print("File not found: " + filename, file=sys.stderr)
        sys.exit(1)

    with open(filename) as f:
        contents = f.read()

    soup = BeautifulSoup(contents, "lxml")
    body = "".join([str(tag) for tag in soup.body])
    body = JEKYLL_HEADER + body

    print("Rewriting " + filename)
    with open(filename, "w") as f:
        f.write(body)


def munge_css(filename):

    if not os.path.exists(filename):
        print("File not found: " + filename, file=sys.stderr)
        sys.exit(1)

    with open(filename) as f:
        contents = f.read()

    contents = SCSS_HEADER + contents + SCSS_FOOTER
    new_css = sassify(contents)

    print("Rewriting " + filename)
    with open(filename, 'w') as f:
        f.write(new_css)


def sassify(scss_string):
    scss = subprocess.Popen(
        ['scss', '-s'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        universal_newlines=True,
    )
    stdout, stderr = scss.communicate(scss_string)
    return stdout


if __name__ == "__main__":

    if os.path.exists('html'):
        print("Refusing to overwrite existing html/ folder", file=sys.stderr)
        sys.exit(1)

    print("Generating CSS with gnome-doc-tool...", file=sys.stderr)
    subprocess.check_call(['gnome-doc-tool', 'css'])

    print("Generating HTML with gnome-doc-tool...", file=sys.stderr)
    subprocess.check_call(['gnome-doc-tool', 'html', '-c', 'index.css',
                           '--copy-graphics', '*.page'])

    os.mkdir('html')
    for filename in glob.glob('*.html'):
        munge_html(filename)
        os.rename(filename, os.path.join('html', filename))

    munge_css('index.css')
    os.rename('index.css', os.path.join('html', 'index.css'))

    print("Embeddable documentation written to html/", file=sys.stderr)
