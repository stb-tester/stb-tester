#!/usr/bin/env python3

"""Strip outputs from an IPython Notebook

Opens a notebook, strips its output, and writes the outputless version to the
original file. Useful mainly as a git pre-commit hook for users who don't want
to track output in VCS. This does mostly the same thing as the "Clear All
Output" command in the notebook UI. Adapted from
https://gist.github.com/minrk/6176788 to work with git filter driver

Set it up with::

    echo "*.ipynb filter=nbstrip" >> .gitattributes
    git config filter.nbstrip.clean extra/nbstripout.py
    git config filter.nbstrip.smudge cat

"""

import sys

from nbformat import v4  # pylint: disable=import-error,no-name-in-module


def strip_output(nb):
    """Strip the outputs from a notebook object"""
    for cell in nb.cells:
        if 'outputs' in cell:
            cell['outputs'] = []
        if 'execution_count' in cell:
            cell['execution_count'] = 0
    return nb


if __name__ == '__main__':
    notebook = v4.reads(sys.stdin.read())
    notebook = strip_output(notebook)
    sys.stdout.write(v4.writes(notebook))
