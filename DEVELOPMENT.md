# Developer Guide

## Project structure

```
ansible-ssh.py          # canonical source file (entry point logic + bash completion)
src/ssh_ansible/
    ansible_ssh.py      # symlink → ../../ansible-ssh.py
    __init__.py
pyproject.toml          # build configuration (PEP 517/518)
.github/workflows/
    build_pypi.yml      # CI: build on every PR/tag, publish on version tags
utils/                  # local helper scripts (gitignored, not shared)
    inst.sh             # symlink ansible-ssh.py into $PATH + install bash completion
    uninst.sh           # remove symlink + bash completion
    requirements.txt    # dev/build dependencies (mirrors pyproject.toml [dev])
```

> **Note:** `ansible-ssh.py` at the repo root is the single source of truth.
> `src/ssh_ansible/ansible_ssh.py` is a symlink to it — edit only the root file.

---

## Local build

### Prerequisites

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip build setuptools-scm twine
```

Or use the project's declared dev extras:

```bash
pip install -e ".[dev]"
```

### Build the wheel

```bash
python -m build --wheel
```

The wheel lands in `dist/`. The version is derived automatically from git tags via
[setuptools-scm](https://setuptools-scm.readthedocs.io/):

| git state | example version |
|-----------|----------------|
| exactly on tag `v1.2.3` | `1.2.3` |
| 5 commits after `v1.2.3` | `1.2.4.dev5+gabcdef1` |

> **Important:** `python -m build` requires the full git history to resolve tags.
> Always use `git fetch --tags` before building if you cloned with `--depth`.

### Validate the package

```bash
twine check dist/*
```

### Clean build artefacts

```bash
rm -rf dist/ build/ src/*.egg-info
```

---

## Versioning

Versions are managed exclusively via **annotated git tags** — there is no version
string in any source file.

```bash
# Tag a new release
git tag -a v1.2.3 -m "Release v1.2.3"
git push origin v1.2.3
```

Pushing a `v*` tag triggers the CI pipeline which builds and publishes to PyPI
automatically (see [CI pipeline](#ci-pipeline) below).

---

## Local installation (development)

`utils/inst.sh` installs the tool from the working tree for manual testing:

```bash
bash utils/inst.sh
```

What it does:
1. Creates `~/.local/bin/ansible-ssh` as a symlink to `ansible-ssh.py` in this repo.
2. Generates the bash completion script and writes it to `/etc/bash_completion.d/ansible-ssh`.
3. Sources the completion script in the current shell.

To uninstall:

```bash
bash utils/uninst.sh
```

---

## CI pipeline (`.github/workflows/build_pypi.yml`)

### Triggers

| Event | Build job | Publish job |
|-------|-----------|-------------|
| Pull request → `main` | ✅ | ❌ |
| Push of a `v*` tag | ✅ | ✅ |
| `workflow_dispatch` | ✅ | ✅ |

### Build job

1. Checks out with `fetch-depth: 0` so setuptools-scm can walk the full tag history.
2. Installs `build` and `twine`.
3. Runs `python -m build` — produces both a wheel and a sdist in `dist/`.
4. Validates the package with `twine check dist/*`.
5. Uploads `dist/` as a workflow artifact.

### Publish job

Runs only on `v*` tags (or `workflow_dispatch`). Uses
[OIDC Trusted Publishing](https://docs.pypi.org/trusted-publishers/) — no API token
or secret is required.

### Release workflow

```bash
# 1. Merge all changes into main
git checkout main
git merge review

# 2. Tag the release
git tag -a v1.1.0 -m "Release v1.1.0"

# 3. Push main and the tag
git push origin main
git push origin v1.1.0
```

The CI pipeline picks up the tag, builds `ssh_ansible-1.1.0-py3-none-any.whl`, and
publishes it to PyPI via OIDC — no manual upload needed.
