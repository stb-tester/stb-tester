import argparse
import subprocess
import sys
import urlparse


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--appliance", help="The URL of your stb-tester ONE appliance")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        'sync', help="Synchronise your working directory with an appliance")

    cmdline_args = parser.parse_args(argv[1:])

    if cmdline_args.appliance is not None:
        u = urlparse.urlparse(cmdline_args.appliance)
        if u.scheme == 'http':
            hostname = u.netloc
        elif u.scheme == '':
            hostname = cmdline_args.appliance
        else:
            sys.stderr.write(
                "Appliance argument must be of the form "
                "http://<hostname>[:port]/ or <hostname>.  Did not understand "
                "%r\n" % cmdline_args.appliance)
            return 1
    else:
        # In the future we can try harder to find out the upstream hostname,
        # e.g. using git remotes or zeroconf
        sys.stderr.write("No appliance name specified\n")
        return 1

    if cmdline_args.command == 'sync':
        if cmdline_args.appliance:
            m = re.match('http://(.*)/.*')
            hostname = m.group(1)
        sync(cmdline_args.appliance)
    return 1


def sync(hostname):
    remote = "http://%s/git/test-pack.git" % hostname
    repo = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'])
    remote_branch_name = "sync/" + subprocess.check_output(
        ['git', 'config', 'user.email'], curdir=repo)

    def update():
        commit_sha = git_snapshot(repo)
        subprocess.check_output(['git', 'push', '--force', remote, '%s:%s' % (
            commit_sha, remote_branch_name)], curdir=repo)

    try:
        update()
        with watch(repo) as filesystem_events:
            for _ in debounce(filesystem_events):
                update()
    finally:
        subprocess.check_output(
            ['git', 'push', remote, ':%s' % remote_branch_name])


def debounce(iterable, timeout=1):
    last_event_time = time.time()
    for x in iterable:
        event_time = time.time()
        if event_time > last_event_time + timeout:
            yield True
        last_event_time = event_time


@contextmanager
def watch(directory):
    import watchdog
    from watchdog.observers import Observer
    import Queue

    q = Queue.Queue()

    def queue_iter():
        while True:
            end, item = q.get()
            if end:
                return
            else:
                yield item

    class QueuingEventHandler(watchdog.events.FileSystemEvent):
        def on_any_event(self, event):
            q.put((False, event))

    observer = watchdog.observers.Observer()
    observer.schedule(QueuingEventHandler(), directory, recursive=True)
    try:
        observer.start()
        yield q
    finally:
        q.put((True, None))
        observer.stop()
    observer.join()


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
