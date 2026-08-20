# Dependency Management

This file documents how dependencies are managed for this project.

Relevant files:
* pyproject.toml - standard file for Python project metadata and dependency
  management
* `requirements.txt` - list of the *pinned* dependencies for this project's CI
  environment

## pyproject.toml

Follow standard practices in this file. Core dependencies should be added to
"project.depedencies". Dependencies for extensions or optional features should
be added to "project.optional-dependencies". For example, specific RCU or power
control implementations. Development dependencies such a linting tools or
packages used by unit tests only should be added to a relevant group in
"dependency-groups".

To generate the complete set of dependencies for the CI environment, run the
following command:

```bash
$ uv export --format requirements.txt --no-header --no-hashes --no-editable --all-extras --all-groups --no-emit-project --output-file requirements.txt
```

At present it is not possible to generate `requirements.txt` using
pip/pip-tools, as they do not support "dependency-groups" in pyproject.toml.

To update an existing dependency's pin, run the above command with
`--upgrade-package=<package>`, e.g.

```bash
$ uv export --format requirements.txt --no-header --no-hashes --no-editable --all-extras --all-groups --no-emit-project --output-file requirements.txt --upgrade-package=pytest
```

Do not edit `requirements.txt` manually.

Note that this project does not use `uv` in another other capacity than to
generate `requirements.txt`, at present. However, a `uv.lock` file is also
tracked by git as this is how `uv` tracks the pinned depedencies. This file
should also not be edited manually.
