Contributing to stb-tester
==========================

Our preferred workflow is via GitHub Pull Requests.

Feel free to open a pull request if you want to start a discussion even if your
implementation isn't complete (but please make it clear that this is the case;
we like GitHub's [TODO lists] for works in progress).

Here are a few guidelines to keep in mind when submitting a pull request:

* Clean commit history: Keep refactorings and functional changes in separate
  commits.

* Commit messages: Short one-line summary, followed by blank line, followed by
  as many paragraphs of explanation as needed. Think of the reviewer when
  you're writing this: This is the place to clarify any subtleties in your
  implementation and to document other approaches you tried that didn't work,
  any limitations of your implementation, etc etc. Most importantly describe
  *why* you made the change, not just *what* the change is.

* If your change is visible to users, please add a bullet point in
  `docs/release-notes.md` under the next unreleased version. Keep this succint
  and think of what a *user* of stb-tester needs to know.

  If you're not very confident in your English, you can skip this step and we
  will be happy to write the release note for your change.

* Ensure that `make check` passes.

    * We use GitHub Actions to automatically run `make check` on all  pull requests.

    * These will work "for free" on your fork of the repository.

* New features must be accompanied by self-tests.

    * If your change is a bug-fix, write a regression test if feasible.

    * We write Python unit tests using [pytest]: Just add a function named
      `test_*` in the appropriate Python file under `tests/`, and use `assert`
      to indicate test failure.

    * We write end-to-end tests in bash: See the functions named `test_*` in
      `tests/test-*.sh`.

* If you add new run-time dependencies:

    * The dependencies should be available in the Ubuntu repositories for all
      [Ubuntu current releases].

    * Add the dependencies to the Dockerfile used to run CI at
      `.github/workflows/ubuntu2204.dockerfile`

Finally, please be patient with us if the review process takes a while. We
really do appreciate your contribution.


[TODO lists]: https://github.com/blog/1375%0A-task-lists-in-gfm-issues-pulls-comments
[pytest]: https://pytest.org/
[GitHub branches view]: https://github.com/stb-tester/stb-tester/branches
[Ubuntu current releases]: https://wiki.ubuntu.com/Releases#Current
[MAINTAINERS.md]: https://github.com/stb-tester/stb-tester/blob/master/MAINTAINERS.md
