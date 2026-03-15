# Release Process

## How to publish a new version of whoopyy to PyPI

### Accounts
- PyPI: `ponderrr` (raponder.business@gmail.com)
- TestPyPI: `pondertest` (raponder.business@gmail.com)
- GitHub: `ponderrr`

### Steps

1. **Bump the version in all three places:**
   - `src/__init__.py` → `__version__ = "X.Y.Z"`
   - `setup.py` → `version="X.Y.Z"`
   - `pyproject.toml` → `version = "X.Y.Z"`

2. **Update CHANGELOG.md** — add a `## [X.Y.Z]` section

3. **Commit and push:**
   ```bash
   git add -A
   git commit -m "chore: bump version to vX.Y.Z"
   git push origin main
   ```

4. **Create a GitHub Release:**
   - Go to https://github.com/ponderrr/whoopyy/releases/new
   - Tag: `vX.Y.Z`
   - Title: `vX.Y.Z — Brief description`
   - Body: paste the relevant CHANGELOG.md section
   - Click **Publish release**

5. **The publish workflow fires automatically:**
   - Tests run (382 tests, 0 failures)
   - Package builds + `twine check`
   - Publishes to TestPyPI
   - Installs from TestPyPI and verifies all imports
   - **Pauses for manual approval**
   - Publishes to PyPI
   - Installs from PyPI and verifies

6. **Approve the PyPI deploy:**
   - Go to Actions tab → the running workflow
   - Click "Review deployments" → approve `pypi` environment

### Versioning (semver)
- **PATCH** (0.3.x) — bug fixes, no API changes
- **MINOR** (0.x.0) — new features, backwards compatible
- **MAJOR** (x.0.0) — breaking API changes

### Current state
- Version: 0.3.1
- License: GPL v3
- PyPI: https://pypi.org/project/whoopyy/
- TestPyPI: https://test.pypi.org/project/whoopyy/
