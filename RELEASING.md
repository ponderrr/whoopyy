# Releasing whoopyy

This runbook publishes **whoopyy 0.4.0**, the first version to go to PyPI. The upload runs in
GitHub Actions (`.github/workflows/publish.yml`) through PyPI
[trusted publishing](https://docs.pypi.org/trusted-publishers/), so no API token is stored
anywhere. Section 1 is one-time setup, section 2 is the pre-release checklist, and section 3 is
the release itself. For later releases, see [Later releases](#later-releases).

## Current state

As of 2026-10-06:

| | |
|---|---|
| Version in source | `0.4.0` in `pyproject.toml`, `setup.py` and `src/__init__.py` on branch `release/0.4.0`. **Not released.** `main` (`2555601`) still holds the 0.3.1 code. `release/0.4.0` has not been pushed (the remote has only `main`), so there is no release PR yet |
| PyPI / TestPyPI | `whoopyy` does not exist on either index (both JSON APIs return 404). Nothing has been uploaded |
| GitHub releases | `v0.2.0`, `v0.3.0` and `v0.3.1` (marked Latest). All three send data calls to WHOOP's retired `/developer/v1` API |
| Publish workflow | Has never run. It was added in `2555601`, after `v0.3.1` was tagged |
| GitHub environments | None. `testpypi` and `pypi` still need to be created ([1.3](#13-create-the-github-environments)) |
| Branch protection | `main` is not protected. The last two CI runs on `main` (2026-03-15) failed under the old `ci.yml`, which `release/0.4.0` replaces |
| Tests | 895 collected: 871 pass and 24 skip (Python 3.9 and 3.13). The 24 skips are `tests/integration/test_real_api.py`, which needs real WHOOP credentials. CI runs Python 3.9 to 3.13, enforces 90% coverage and runs `mypy --strict` |
| Package build | `python -m build` plus `twine check` pass. The wheel contains `whoopyy/py.typed`, and mypy picks up its types from an installed copy (checked locally on 2026-10-06) |
| License | GPL-3.0-only |

Run the test suite again before you release. The auth-hardening work on another branch will
change these numbers when it merges.

## How the publish workflow runs

`publish.yml` (workflow name "Publish to PyPI") runs on `release: types: [published]`.
Publishing a GitHub release starts it, and so does publishing a draft or a pre-release.
GitHub uses the copy of `publish.yml` in the tagged commit, so merge any change to the workflow
before you tag.

| Job id | Shown as | Needs | Environment | What it does |
|---|---|---|---|---|
| `test` | Run test suite | | | Python 3.11: `pip install -e ".[dev]"`, `pytest --tb=short -q`, `mypy src/ --ignore-missing-imports` |
| `build` | Build distribution | `test` | | Fails unless the release tag equals `v` + the `pyproject.toml` version, then `python -m build`, `twine check dist/*`, and uploads artifact `dist` (kept 7 days) |
| `publish-testpypi` | Publish to TestPyPI | `build` | `testpypi` | `pypa/gh-action-pypi-publish@release/v1` to `https://test.pypi.org/legacy/` with `skip-existing: true`. `permissions: id-token: write` |
| `verify-testpypi` | Verify TestPyPI install | `publish-testpypi` | | `pip install whoopyy==<tag version>` from TestPyPI (dependencies from PyPI), retrying every 30 s up to 10 times, then imports the clients, models and exceptions |
| `publish-pypi` | Publish to PyPI | `verify-testpypi` | `pypi` | `pypa/gh-action-pypi-publish@release/v1` to PyPI. `permissions: id-token: write` |
| `verify-pypi` | Verify PyPI install | `publish-pypi` | | `pip install whoopyy==<tag version>`, retrying every 30 s up to 10 times, then imports the clients |

PyPI and GitHub must agree on these values:

| Setting | Value |
|---|---|
| Project name (PyPI and TestPyPI) | `whoopyy` |
| GitHub owner | `ponderrr` |
| GitHub repository | `whoopyy` |
| Workflow file | `publish.yml` |
| Environment for the TestPyPI publisher | `testpypi` |
| Environment for the PyPI publisher | `pypi` |

## 1. One-time setup

### 1.1 PyPI and TestPyPI accounts

TestPyPI is a separate site with its own accounts. You need both, because the workflow uploads
to TestPyPI before PyPI.

| Site | Account |
|---|---|
| https://pypi.org | `ponderrr` (raponder.business@gmail.com) |
| https://test.pypi.org | `pondertest` (raponder.business@gmail.com) |

On each site:

1. Register, or sign in if the account already exists.
2. Verify the email address. The pending-publisher form's **Add** button stays disabled until
   the account has a verified primary email.
3. Turn on two-factor authentication under Account settings → Two factor authentication (2FA).
   PyPI requires 2FA on every account. Keep the recovery codes somewhere safe.

Sign in as the account that should own the project. Whoever adds the pending publisher becomes
the owner of `whoopyy` when the first upload succeeds.

### 1.2 Register pending trusted publishers

The project doesn't exist yet, so you add a *pending* publisher. It becomes an ordinary
publisher after the first successful upload.

**PyPI.** Open https://pypi.org/manage/account/publishing/ (Your account → Publishing), choose
the **GitHub** tab, and fill in:

| Field | Value |
|---|---|
| PyPI Project Name | `whoopyy` |
| Owner | `ponderrr` |
| Repository name | `whoopyy` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

Click **Add**.

**TestPyPI.** Repeat at https://test.pypi.org/manage/account/publishing/ signed in as the
TestPyPI account. There the first field is called **TestPyPI Project Name**. Use the same values,
except **Environment name** is `testpypi`.

Things to watch:

- **Workflow name** takes the bare file name `publish.yml`, not `.github/workflows/publish.yml`.
- PyPI marks **Environment name** as optional, but `publish.yml` runs each upload job in an
  environment, so fill it in. It must match the job's `environment.name`; PyPI ignores case.
  The likeliest mistake is swapping `pypi` and `testpypi`.
- A pending publisher doesn't reserve the name. If someone else registers `whoopyy` first,
  PyPI invalidates your pending publisher ([5.2](#52-trusted-publisher-errors)).
- `publish-testpypi` runs first, so a missing or wrong TestPyPI publisher is the first thing
  that fails.

### 1.3 Create the GitHub environments

`publish-testpypi` runs in environment `testpypi` and `publish-pypi` in `pypi`. If an environment
is missing, GitHub creates it when the job starts, **with no protection rules**, and the PyPI
upload then runs without waiting for you. Create both environments before you release.

In the browser, go to **Settings → Environments → New environment**, enter `pypi`, click
**Configure environment**, and then:

1. Tick **Required reviewers** and add `ponderrr`.
2. Leave **Prevent self-review** unticked. You publish the release and you also approve the
   deployment, so with it ticked nobody can approve.
3. Under **Deployment branches and tags**, choose **Selected branches and tags** and add a rule
   with **Ref type** set to Tag and the name pattern `v*`. Avoid **Protected branches only**: the
   release run's ref is the tag `refs/tags/v0.4.0`, which isn't a branch, so GitHub would refuse
   the job. **No restriction** also works.
4. Click **Save protection rules**.

Repeat for `testpypi`. A reviewer on `testpypi` is optional. With one, you approve twice per
release: once before the TestPyPI upload and once before PyPI. Without one, only the PyPI upload
waits for you.

To do the same from a terminal:

```bash
ME_ID=$(gh api users/ponderrr --jq .id)
for ENV in testpypi pypi; do
  gh api -X PUT "repos/ponderrr/whoopyy/environments/$ENV" --input - <<JSON
{
  "reviewers": [{"type": "User", "id": $ME_ID}],
  "prevent_self_review": false,
  "deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}
}
JSON
  gh api -X POST "repos/ponderrr/whoopyy/environments/$ENV/deployment-branch-policies" \
    -f name='v*' -f type=tag
done

# Each environment should list required_reviewers and branch_policy
gh api repos/ponderrr/whoopyy/environments \
  --jq '.environments[] | {name, rules: [.protection_rules[].type]}'
```

Required reviewers cost nothing on public repositories, and whoopyy is public.

### 1.4 (Optional) Protect `main`

You can require CI to pass before anything merges to `main`. `ci.yml` (workflow "CI") reports
six checks:

- `Tests (Python 3.9)`, `Tests (Python 3.10)`, `Tests (Python 3.11)`, `Tests (Python 3.12)`,
  `Tests (Python 3.13)`, from the `test` matrix job
- `Type check, version, package`, from the `checks` job

GitHub lists a check in the picker only after it has run in the repository recently. These
names come from the new `ci.yml` on `release/0.4.0`, so open the release PR
([section 2](#2-pre-release-checklist)) first. Then go to **Settings → Branches → Add classic
branch protection rule**, enter the branch name pattern `main`, tick **Require status checks to
pass before merging**, add the six checks, and save. From a terminal:

```bash
gh api -X PUT repos/ponderrr/whoopyy/branches/main/protection --input - <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "Tests (Python 3.9)", "Tests (Python 3.10)", "Tests (Python 3.11)",
      "Tests (Python 3.12)", "Tests (Python 3.13)",
      "Type check, version, package"
    ]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null
}
JSON
```

With `enforce_admins: false` you can still bypass the rule as an admin in an emergency. If the
Python matrix in `ci.yml` changes, update this list. Otherwise merges wait on a check that never
runs.

## 2. Pre-release checklist

Open the release PR if it doesn't exist yet:

```bash
git push -u origin release/0.4.0
gh pr create --repo ponderrr/whoopyy --base main --head release/0.4.0 \
  --title "Release 0.4.0: back to the WHOOP v2 API" \
  --body "See CHANGELOG.md, section 0.4.0."
gh pr checks release/0.4.0 --repo ponderrr/whoopyy --watch
```

- [ ] **CI is green on the release PR.** All six checks from [1.4](#14-optional-protect-main)
  pass.
- [ ] **The live check passes against your own WHOOP account.** `scripts/live_check.py` makes
  GET requests only and checks every read endpoint's raw response against the 0.4.0 models.
  `python scripts/live_check.py --help` lists the current options. You need a WHOOP developer
  app whose redirect URLs include `http://localhost:8080/callback`; run the script without
  credentials and it prints how to create one. Run it from the `release/0.4.0` checkout, in a
  virtualenv with that checkout installed, so it tests this code and not another whoopyy:

  ```bash
  python3 -m venv .venv && . .venv/bin/activate
  pip install -e .                 # whoopyy 0.4.0 from the release/0.4.0 checkout
  export WHOOP_CLIENT_ID=...       # your WHOOP developer app
  export WHOOP_CLIENT_SECRET=...
  # export WHOOP_REDIRECT_URI=http://localhost:<port>/callback  # only if your app registers a different redirect than http://localhost:8080/callback
  python scripts/live_check.py     # signs in through your browser
  echo $?                          # 0 = every endpoint was called and validated
  ```

  The first lines name the whoopyy it imported. If they include `note: this is not the whoopyy
  checkout the script lives in`, activate the virtualenv above and run it again. Exit code 0
  allows only `workout` and `activity_mapping` to be skipped (no workout, or no legacy `v1_id`,
  in the window). If `cycle`, `recovery_for_cycle`, `sleep` or `sleep_for_cycle` fail with "not
  verified", the window had no data; run again with `--days 30`.

  If it exits with 1 after `Sign-in failed`, fix the app's redirect URL or scopes; no report is
  written in that case. Otherwise read `shape_report.json` in the output directory: it has the
  failing endpoint, the field path, any fields the models don't declare and any values pydantic
  only accepted by coercing their type. The `raw/` directory next to it holds your health data,
  so don't share or commit it. The integration suite covers similar ground: export
  `WHOOP_CLIENT_ID`, `WHOOP_CLIENT_SECRET` and `WHOOP_REFRESH_TOKEN`, then run
  `pytest tests/integration/ -v --tb=long`. Neither runs in CI, so this is the only test against
  the real API.
- [ ] **The distribution name is final.** The first upload, to TestPyPI and then PyPI, creates
  the project under the `name` in `pyproject.toml`. PyPI can't rename a project: a new name means
  a second project, with the old one left behind. `whoopyy` contains WHOOP's trademark, and
  WHOOP's API terms effective 2026-10-06 removed the brand license. Whether to keep the name is
  your call; this is not legal advice. The README already ends with an "unofficial SDK" and
  trademark line. You could also put "not affiliated with or endorsed by WHOOP" in the
  `description` in `pyproject.toml`, which PyPI shows as the summary. If you rename, change all
  of these before you tag:
  - `name` in `pyproject.toml` and `setup.py`.
  - `whoopyy==$VERSION` in `publish.yml`. `verify-testpypi` and `verify-pypi` install by
    name, so they break if this isn't changed. Also change the two `environment.url` values.
  - **PyPI Project Name** on both pending publishers.
  - The install instructions in `README.md`.

  The import name (`import whoopyy`) comes from `packages=["whoopyy"]` in `setup.py` and can
  stay as it is.
- [ ] **README and CHANGELOG are accurate.**
  - The 0.4.0 entry in `CHANGELOG.md` matches what the live check showed: v2 paths, UUID
    sleep and workout IDs, `step_count`, `sport_name`.
  - The heading reads `## [0.4.0] - 2026-10-06`. If you release on another day, change the
    date, and change the README link `CHANGELOG.md#040---2026-10-06` (in the "Upgrading from
    0.2.x / 0.3.x?" note) to match.
  - The README's project-structure tree still says "360+ tests, 90% coverage".
  - PyPI shows `README.md` as the project page. Relative links (`CHANGELOG.md`, `LICENSE`) and
    Mermaid diagrams don't work there. You'll see the rendered page on TestPyPI in
    [3.4](#34-watch-the-run-and-approve) before you approve the PyPI upload.
- [ ] **The version is consistent.**

  ```bash
  grep -n '0\.4\.0' pyproject.toml setup.py src/__init__.py
  grep -n '^## \[0\.4\.0\]' CHANGELOG.md
  ```

  The `Type check, version, package` CI check fails if the three files disagree. Nothing checks
  the tag against the version, so make sure the tag is exactly `v0.4.0`.
- [ ] **(Optional) Local build dry run.** This is the same thing the `build` job does:

  ```bash
  pip install build twine
  rm -rf dist && python -m build && twine check dist/*
  python -m zipfile -l dist/*.whl | grep whoopyy/py.typed
  ```

## 3. Release

### 3.1 Merge to `main`

```bash
gh pr merge release/0.4.0 --repo ponderrr/whoopyy --merge
git fetch origin
gh run list --repo ponderrr/whoopyy --workflow ci.yml --commit "$(git rev-parse origin/main)" --limit 1
gh run watch <run-id> --repo ponderrr/whoopyy --exit-status
```

`--commit` picks the run for the merge commit. The push-triggered run takes a few seconds to
register, so if the list is empty, run `gh run list` again. Filtering by `--branch main` alone
can return the previous run on `main` (today, a failed run from 2026-03-15).

Wait for CI on `main` to pass before you tag.

### 3.2 Tag `v0.4.0`

Run these in your main checkout:

```bash
git fetch origin
git show origin/main:pyproject.toml | grep '^version'   # expect: version = "0.4.0"
git tag -a v0.4.0 -m "whoopyy 0.4.0" origin/main
git push origin v0.4.0
```

Pushing the tag doesn't start anything: CI runs on branch pushes and PRs, and `publish.yml`
waits for a release.

### 3.3 Create the GitHub release

This is the step that starts the publish workflow. Everything before it can be undone.

```bash
git show v0.4.0:CHANGELOG.md \
  | awk '/^## \[0\.4\.0\]/{found=1; next} /^## \[/{if (found) exit} found' \
  > /tmp/whoopyy-0.4.0-notes.md

gh release create v0.4.0 --repo ponderrr/whoopyy --verify-tag \
  --title "v0.4.0 — Back to the WHOOP v2 API" \
  --notes-file /tmp/whoopyy-0.4.0-notes.md
```

- The `awk` command extracts the body of the 0.4.0 section, without its heading.
- `--verify-tag` stops if the tag isn't on GitHub, rather than creating a new tag from `main`.
- Leave out `--prerelease`. A published pre-release starts the workflow too, and PyPI would get
  an ordinary 0.4.0.
- To proofread first, add `--draft`, review the release on GitHub, then run
  `gh release edit v0.4.0 --repo ponderrr/whoopyy --draft=false`. Publishing the draft starts
  the workflow.

### 3.4 Watch the run and approve

```bash
RUN_ID=$(gh run list --repo ponderrr/whoopyy --workflow publish.yml --event release \
  --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID" --repo ponderrr/whoopyy --exit-status
```

The run takes a few seconds to appear after you publish the release. It goes through `test` →
`build` → `publish-testpypi` (waits for approval if `testpypi` has a reviewer) →
`verify-testpypi` → `publish-pypi` (waits for approval) → `verify-pypi`.

To approve in the browser, run `gh run view "$RUN_ID" --repo ponderrr/whoopyy --web`, click
**Review deployments**, tick the environment and click **Approve and deploy**. To approve from a
terminal:

```bash
ENV_NAME=testpypi   # first approval; run again with ENV_NAME=pypi after verify-testpypi passes
gh api "repos/ponderrr/whoopyy/actions/runs/$RUN_ID/pending_deployments" \
  --jq '.[] | "\(.environment.name) \(.environment.id)"'
ENV_ID=$(gh api "repos/ponderrr/whoopyy/actions/runs/$RUN_ID/pending_deployments" \
  --jq ".[] | select(.environment.name == \"$ENV_NAME\") | .environment.id")
if [ -n "$ENV_ID" ]; then
  gh api -X POST "repos/ponderrr/whoopyy/actions/runs/$RUN_ID/pending_deployments" \
    -F "environment_ids[]=$ENV_ID" -f state=approved -f comment="Release 0.4.0"
else
  echo "$ENV_NAME is not waiting for approval"
fi
```

Only the environment whose job is waiting appears in `pending_deployments`, so the first
approval is `testpypi` (if it has a reviewer, as the terminal setup in
[1.3](#13-create-the-github-environments) gives it) and the second is `pypi`. Without a
reviewer on `testpypi`, start with `ENV_NAME=pypi`. Keep `environment_ids[]=...` in quotes,
because zsh treats unquoted `[]` as a glob.

Before you approve `pypi`, check two things:

- The `verify-testpypi` log shows `whoopyy version: 0.4.0` and `All imports successful`. The
  install isn't pinned to a version, so read the version line.
- https://test.pypi.org/project/whoopyy/0.4.0/ renders the README and shows the GPL-3.0-only
  license and Python >=3.9.

This is your last chance to stop. If you reject `pypi`, nothing reaches PyPI. TestPyPI keeps
0.4.0, which does no harm.

### 3.5 Verify on PyPI

Use a fresh virtualenv:

```bash
D=$(mktemp -d) && cd "$D"
python3 -m venv venv
venv/bin/pip install --no-cache-dir "whoopyy==0.4.0" mypy
venv/bin/python -c "import whoopyy; print(whoopyy.__version__, whoopyy.__file__)"
printf 'import whoopyy\nreveal_type(whoopyy.__version__)\nreveal_type(whoopyy.WhoopClient.get_cycle)\n' > typed_check.py
venv/bin/python -m mypy typed_check.py
```

Expected output (the locally built wheel gave the same result on 2026-10-06):

```text
0.4.0 /.../venv/lib/python3.X/site-packages/whoopyy/__init__.py
typed_check.py:2: note: Revealed type is "str"
typed_check.py:3: note: Revealed type is "def (self: whoopyy.client.WhoopClient, cycle_id: int) -> whoopyy.models.Cycle"
Success: no issues found in 1 source file
```

mypy 1.x, which is what pip installs on Python 3.9 (the macOS `/usr/bin/python3`), prints
`builtins.str` and `cycle_id: builtins.int` instead of `str` and `cycle_id: int`. Either is
fine: the check passes as long as mypy reveals these types and doesn't print `missing library
stubs or py.typed marker`.

If mypy instead says `Skipping analyzing "whoopyy": module is installed, but missing library
stubs or py.typed marker`, the wheel has no `py.typed`. Yank the release
([5.7](#57-yanking-a-bad-release)) and fix it. If pip says `No matching distribution found`,
PyPI's CDN hasn't caught up yet; wait a minute and try again.

Also look at https://pypi.org/project/whoopyy/: the README should render and the license and
Python requirement should be right. The SHA-256 hashes printed by `publish-pypi`
(`print-hash: true`) should match the hashes listed under "Download files".

## 4. Post-release

### 4.1 Warn on the old releases

The old releases stay up on GitHub, and until now `v0.3.1` was marked Latest. Add a warning to
the top of its notes:

```bash
cat > /tmp/v1-warning.md <<'EOF'
> **Do not use this release.** It sends its data calls to WHOOP's retired `/developer/v1` API, so they no longer work. Use [v0.4.0](https://github.com/ponderrr/whoopyy/releases/tag/v0.4.0) or later (`pip install -U whoopyy`). The [0.4.0 changelog](https://github.com/ponderrr/whoopyy/blob/main/CHANGELOG.md#040---2026-10-06) has migration notes.

EOF
gh release view v0.3.1 --repo ponderrr/whoopyy --json body --jq .body > /tmp/v0.3.1-body.md
cat /tmp/v1-warning.md /tmp/v0.3.1-body.md > /tmp/v0.3.1-notes.md
gh release edit v0.3.1 --repo ponderrr/whoopyy --notes-file /tmp/v0.3.1-notes.md
```

`v0.3.0` and `v0.2.0` have the same problem, since every version from 0.2.0 to 0.3.1 targets
v1. Repeat the steps with those tags. None of them was ever on PyPI, so there is nothing to yank.

Then run `gh release list --repo ponderrr/whoopyy`. `v0.4.0` should be marked Latest. If it
isn't, run `gh release edit v0.4.0 --repo ponderrr/whoopyy --latest`.

### 4.2 Housekeeping

- On PyPI, go to Your projects → whoopyy → Manage → Publishing. The publisher should now be
  listed against the project, and the pending entry should be gone. Check TestPyPI the same way.
- Update [Current state](#current-state) in this file, and start an `## [Unreleased]` section
  in `CHANGELOG.md`.

### 4.3 Announce

- The GitHub release notifies everyone watching the repository. Anyone on 0.2.0 to 0.3.1
  installed it from GitHub, since those versions were never on PyPI. Their data calls fail, and
  they should run `pip install -U whoopyy`.
- If you like, pin a GitHub issue with the same message and post it wherever you've shared the
  project. Don't claim more than the CHANGELOG says.

## 5. Troubleshooting

To read the log of a failed job, run `gh run view "$RUN_ID" --repo ponderrr/whoopyy --log-failed`.

### 5.1 The workflow didn't start

- The release is still a draft. Publish it.
- A workflow created the release using `GITHUB_TOKEN`. Releases created that way don't start
  other workflows. Create the release with `gh` or in the web UI.
- The tagged commit doesn't contain `.github/workflows/publish.yml`, because GitHub reads the
  workflow from the tagged commit. This is why the `v0.3.1` release never ran it.

### 5.2 Trusted publisher errors

The upload job fails with a message like this:

```text
Trusted publishing exchange failure:
Token request failed: the server refused the request for the following reasons:

* `invalid-publisher`: valid token, but no corresponding publisher (Publisher with matching claims was not found)
```

Below that, the log prints the token's claims. For this repository they should read:

- `repository`: `ponderrr/whoopyy`
- `repository_owner`: `ponderrr`
- `workflow_ref` and `job_workflow_ref`: `ponderrr/whoopyy/.github/workflows/publish.yml@refs/tags/v0.4.0`
- `ref`: `refs/tags/v0.4.0`
- `environment`: `testpypi` in `publish-testpypi`, `pypi` in `publish-pypi`

| Message | Cause | Fix |
|---|---|---|
| `invalid-publisher` ... `(Publisher with matching claims was not found)` | No publisher on that index matches owner + repository + workflow file + environment. Usually the TestPyPI publisher is missing, **Workflow name** was entered as a path, **Environment name** is wrong or `pypi` and `testpypi` are swapped, or there's a typo. A wrong environment gives this message too, not a separate one | On the index the failing job uploads to, add the publisher if it's missing. PyPI can't edit a publisher in place, so otherwise remove it and add it again with the right values (environment `testpypi` on TestPyPI, `pypi` on PyPI). Then re-run failed jobs |
| `invalid-pending-publisher`: `valid token, but project already exists` | `whoopyy` already exists on that index. Pending publishers don't reserve names | If the project is yours, add an ordinary publisher under the project's Manage → Publishing. If not, choose a new name ([section 2](#2-pre-release-checklist)) |
| `OpenID Connect token retrieval failed` | The job is missing `permissions: id-token: write` | Both upload jobs in `publish.yml` have it, so this only happens if the workflow was edited |

See also https://docs.pypi.org/trusted-publishers/troubleshooting/.

### 5.3 Environment problems

| Symptom | Cause | Fix |
|---|---|---|
| The upload ran without stopping at "Waiting for review" | The environment didn't exist, so GitHub created it with no rules, or it has no required reviewer | Set it up as in [1.3](#13-create-the-github-environments) before the next run. If the upload has already happened, verify it ([3.5](#35-verify-on-pypi)) |
| `gh api repos/ponderrr/whoopyy/environments/pypi` returns 404 Not Found | The environment hasn't been created | [1.3](#13-create-the-github-environments) |
| The job fails at once, saying the tag `v0.4.0` is not allowed to deploy to `pypi` (or `testpypi`) due to environment protection rules | **Deployment branches and tags** is set to **Protected branches only**, or no tag rule matches `v0.4.0` | Switch to **Selected branches and tags** with the Tag rule `v*`, or to **No restriction**. Then re-run failed jobs |
| You can't approve your own run | **Prevent self-review** is ticked, or you aren't a required reviewer | Untick it or add yourself. If the run has already failed or been rejected, re-run failed jobs |

### 5.4 `verify-testpypi` can't find the package

`ERROR: No matching distribution found for whoopyy==0.4.0` on every one of the 10 attempts
(about 5 minutes) means TestPyPI's index still hadn't updated. Re-run failed jobs. `verify-pypi`
retries the same way and can fail the same way.

### 5.5 Re-running a failed publish

Use **Re-run failed jobs** in the run's page, or
`gh run rerun "$RUN_ID" --repo ponderrr/whoopyy --failed`. Once `publish-testpypi` has
succeeded, **never** use **Re-run all jobs**. A full re-run builds again and uploads to TestPyPI
again. The rebuilt files aren't byte-identical to the ones already there. `publish-testpypi`
sets `skip-existing: true`, so it skips them instead of failing, but `publish-pypi` would then
upload the *rebuilt* files, which differ from what you verified on TestPyPI. A re-run uses the same commit and `publish.yml` as the original run. Jobs in an
environment need approval again, and the `dist` artifact is kept for only 7 days.

| Failed job | Already uploaded | What to do |
|---|---|---|
| `test` or `build` | Nothing | If it's flaky, re-run failed jobs. For a real bug, fix it in a PR, then delete the release and tag (`gh release delete v0.4.0 --repo ponderrr/whoopyy --cleanup-tag --yes` and `git tag -d v0.4.0`) and redo section 3. Nothing was uploaded, so `v0.4.0` can be reused |
| `publish-testpypi` | Nothing | Fix the TestPyPI publisher ([5.2](#52-trusted-publisher-errors)), then re-run failed jobs |
| `verify-testpypi` | 0.4.0 on TestPyPI | If the index was just slow ([5.4](#54-verify-testpypi-cant-find-the-package)), re-run failed jobs. If the package is broken, don't approve PyPI. Fix it and release 0.4.1, because TestPyPI won't accept the 0.4.0 files again |
| `publish-pypi` | 0.4.0 on TestPyPI | Fix the PyPI publisher, then re-run failed jobs within 7 days |
| `verify-pypi` | 0.4.0 on PyPI | If the index was slow, re-run failed jobs or check by hand ([3.5](#35-verify-on-pypi)). If the package is broken, yank it ([5.7](#57-yanking-a-bad-release)) and release 0.4.1 |

If `publish-pypi` (or `publish-testpypi`) uploaded some files but not all, for example the
wheel but not the sdist, use **Re-run failed jobs** within the 7-day artifact window. The re-run
uploads the same files from the `dist` artifact, and PyPI answers `200 OK` to a file that is
byte-identical to one it already has, so only the missing file is added.

Upload by hand only if the `dist` artifact has expired:

1. Rebuild just the missing file from the tag: `git checkout v0.4.0`, then
   `pip install build twine && python -m build --sdist` (or `--wheel`). A rebuilt file differs
   from the original, which is fine for a file name PyPI has never had, but PyPI refuses it under
   a name it already has.
2. Create an API token scoped to `whoopyy` under PyPI Account settings → API tokens.
3. Run `twine upload dist/whoopyy-0.4.0.tar.gz` (or the wheel). For TestPyPI, use a TestPyPI
   token and add `--repository testpypi`.
4. Delete the token.

### 5.6 Other upload errors

- `400 File already exists`: the index already has a different file under this name. PyPI never
  replaces a file. Re-sending a byte-identical copy is accepted with `200 OK`
  ([5.5](#55-re-running-a-failed-publish)), but a rebuilt file isn't identical. Bump the version.
- `400 This filename was previously used by a file that has since been deleted`: deleting a file
  or release doesn't free its file name. Bump the version.
- An error saying the name isn't allowed or is too similar to an existing project: PyPI blocks
  names that collide with an existing project after normalization. Choose another name
  ([section 2](#2-pre-release-checklist)).

### 5.7 Yanking a bad release

Yank the release rather than deleting it. Once a release is yanked, `pip install whoopyy` and
version ranges skip it, but `pip install whoopyy==0.4.0` still installs it, with a warning. The
files stay on PyPI. Deleting is permanent, and the file names can never be uploaded again.

1. Go to https://pypi.org/manage/project/whoopyy/releases/, open 0.4.0, choose **Options** →
   **Yank**, enter a reason (pip shows it to users), and confirm. You can un-yank from the same
   menu.
2. Edit the GitHub release notes to say the release was yanked and why.
3. Fix the problem, bump to 0.4.1, and release as usual. You can leave the TestPyPI copy as it
   is.

## Later releases

The publishers and environments stay in place, so a later release needs only:

1. Bump the version in `pyproject.toml`, `setup.py` and `src/__init__.py`. CI checks that the
   three match.
2. Rename `## [Unreleased]` in `CHANGELOG.md` to `## [X.Y.Z] - YYYY-MM-DD`.
3. Open a PR, wait for CI to pass, and merge.
4. Tag `vX.Y.Z` on `origin/main` and create the release from that CHANGELOG section, as in
   [3.2](#32-tag-v040) and [3.3](#33-create-the-github-release) with the version changed.
5. Approve and verify as in [3.4](#34-watch-the-run-and-approve) and
   [3.5](#35-verify-on-pypi). The verify jobs install `whoopyy` without a version pin, so check
   that the version they print is the new one.

## Versioning

whoopyy follows [semver](https://semver.org/). While it is on 0.x:

- **MINOR** (0.x.0): new features and breaking changes. 0.3 → 0.4 was a breaking change.
- **PATCH** (0.4.x): bug fixes with no API changes.

From 1.0.0 on, breaking changes bump **MAJOR**.
