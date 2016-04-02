import argparse
import subprocess
import sys


def main(argv):
    parser = argparse.ArgumentParser()
    parser.parse_args(argv[1:])
    return 1


class UnknownFileInRepo(Exception):
    pass


def git_snapshot(repo_dir):
    """
    Takes a snapshot of your git repo working directory creating a new commit
    leaving your git repo otherwise unaffected.  Returns the commit SHA.

    The commit will have the message "snapshot".

    This function will raise UnknownFileInRepo exception if there are files that
    have not been added nor ignored in the repo.

    If there are no changes in the working directory it will just return the
    commit SHA of HEAD.
    """
    def g(*args, **kwargs):
        env = dict(os.environ)
        env.update(kwargs)
        return subprocess.check_output(('git',) + args, cwd=repo_dir, env=env)

    status = [(x[0:2], x[3:]) for x in g('status', '-z').split('\0')]
    for status_code, filename in status:
        if status_code == '??':
            raise UnknownFileInRepo(
                'Cannot snapshot git repo: directory contains unknown file '
                '%s.  Either add it (with git add) or add it to .gitignore'
                % filename)

    base_commit = g('rev-parse', '--verify', 'HEAD').strip()
    # state of the working tree
    with tempfile.NamedTemporaryFile(
            prefix="index-snapshot-") as tmp_index:
        g('add', '-u', GIT_INDEX_FILE=tmp_index.name)
        write_tree = g(
            'write-tree', GIT_INDEX_FILE=tmp_index.name).strip()

    if g('show', '--format=%T', '-s', base_commit).strip() == write_tree:
        return base_commit
    else:
        return g('commit-tree', write_tree, '-p', base_commit,
                '-m', "snapshot").strip()


class GitTestHelper(object):
    def __init__(self):
        from _stbt.utils import named_temporary_directory
        self._tmpdir = named_temporary_directory()

    def __enter__(self):
        self.repo = self._tmpdir.__enter__()
        subprocess.check_call(['git', 'init'], curdir=self.repo)
        with open(d + 'test.txt', 'w') as f:
            f.write('hello')
        subprocess.check_call(['git', 'add', '%s/test.txt' % d],
                              curdir=self.repo)
        subprocess.check_call(['git', 'commit', '-m', 'test'], curdir=self.repo)
        self.orig_commit_sha = self.commit_sha()
        assert self.status() == ''

    def __call__(*args):
        return subprocess.check_output(['git'] + args, curdir=self.repo).strip()

    def commit_sha(self):
        return self('rev-parse', 'HEAD')

    def status(self):
        return self('status', '--porcelain', 'HEAD')

    def cat_file(self, revision, filename):
        return self('cat-file', 'blob', '%s:%s' % (revision, filename))

    def __exit__(*args, **kwargs):
        self._tmpdir.__exit__(*args, **kwargs)


def test_that_git_snapshot_with_no_changes_returns_current_commit():
    with GitTestHelper() as g:
        assert git_snapshot(g.repo) == g.orig_commit_sha
        assert g.commit_sha() == g.orig_commit_sha
        assert g.status() == ''


def test_that_git_snapshot_with_changes_includes_those_changes():
    with GitTestHelper() as g:
        with open('%s/test.txt', 'w') as f:
            f.write('goodbye')
        assert g.status() == ' M test.txt'
        new_sha = git_snapshot(d)
        assert g.status() == ' M test.txt'
        assert g.cat_file(new_sha, 'test.txt') == 'goodbye'
        assert g('merge-base', new_sha, g.orig_commit_sha) == g.orig_commit_sha


def test_that_git_snapshot_doesnt_affect_the_index():
    with GitTestHelper() as g:
        with open('%s/test.txt', 'w') as f:
            f.write('goodbye')
        g('add', 'test.txt')
        assert g.status() == 'M  test.txt'
        new_sha = git_snapshot(d)
        assert g.status() == 'M  test.txt'
        assert g.cat_file(new_sha, 'test.txt') == 'goodbye'


def test_that_git_snapshot_raises_with_unknown_files():
    with GitTestHelper() as g:
        with open('%s/test2.txt', 'w') as f:
            f.write('hello')
        assert g.status() == '?? test2.txt'
        try:
            git_snapshot(g.repo)
        except UnknownFileInRepo:
            pass
        else:
            assert False, "git_snapshot should have thrown"


def test_that_git_snapshot_includes_added_but_unknown_files():
    with GitTestHelper() as g:
        with open('%s/test2.txt', 'w') as f:
            f.write('hello')
        g('add', 'test2.txt')
        assert g.status() == '?A test2.txt'
        new_sha = git_snapshot(g.repo)
        assert g.status() == '?A test2.txt'
        assert g.cat_file(new_sha, 'test2.txt') == 'hello'

if __name__ == '__main__':
    sys.exit(main(sys.argv))
