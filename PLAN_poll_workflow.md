# Plan: Move `check_update_times.py` polling into GitHub Actions

## Context

- `check_update_times.py` polls CDC endpoints and appends a row to
  `update_log.csv` on the `update-time-log` branch. The goal is to build up
  a picture of *when* CDC updates each dataset during the week, so we can
  tune the weekly Discord post's schedule.
- Running the script inside the Claude Code sandbox fails because the
  sandbox's egress proxy blocks/rewrites external HTTPS (the TLS cert
  issuer came back as `Anthropic; CN=sandbox-egress-production TLS
  Inspection CA`, returning 403). So polling from Claude Code agents
  isn't viable — we need a runner with real internet access.
- A `User-Agent: Mozilla/5.0` header was already added to `fetch_json()`
  on `update-time-log` (commit `e943f36`) to work around CDC's block of
  default `Python-urllib` UAs. This may or may not be necessary on
  GitHub's runners — verify empirically.

## Approach

Add a second scheduled GitHub Actions workflow, `poll-update-times.yml`,
that runs `check_update_times.py` on a cron schedule and commits any
resulting row back to `update-time-log`.

Model it on the existing `.github/workflows/weekly-post.yml` — same
checkout/setup-python/install pattern.

## What to build

### 1. New workflow: `.github/workflows/poll-update-times.yml`

Requirements:

- **Trigger**: cron every 6 hours (`0 */6 * * *`) plus
  `workflow_dispatch` for manual runs.
- **Branch**: check out `update-time-log` explicitly (not the default
  branch).
- **Permissions**: `contents: write` so the job can push commits.
- **Steps**:
  1. `actions/checkout@v6` with `ref: update-time-log`.
  2. `actions/setup-python@v6` with Python 3.12.
  3. No dependencies needed — `check_update_times.py` uses only stdlib.
     (Skip `pip install -r requirements.txt`.)
  4. Run `python check_update_times.py`. If it exits non-zero, the job
     should fail and **not** commit — the script already exits without
     writing on fetch failure, but double-check this is still true.
  5. Configure git identity (`github-actions[bot]`).
  6. `git add update_log.csv`. If nothing changed, skip the commit
     (guard with `git diff --cached --quiet || git commit ...`).
  7. `git push origin update-time-log`.
- **Concurrency**: add a `concurrency:` group keyed to the workflow so
  two runs can't race on pushing to the same branch.

### 2. Verify the `User-Agent` fix is actually doing work

Once the workflow runs once successfully, you'll have confirmation that
the UA fix (or lack thereof) works on GitHub's runners. If you're
curious whether GitHub runners would have hit the 403 without it, you
can briefly revert `fetch_json()` and re-run — but this is optional;
the header is harmless.

### 3. Sanity-check `check_update_times.py` before pushing the workflow

On your laptop (where outbound HTTPS works):

```bash
cd contagion-poster
git checkout update-time-log
git pull
python check_update_times.py
```

Expected: exits 0, appends one row to `update_log.csv`, prints
timestamps for wastewater + three Socrata datasets. If this fails,
debug the script before setting up the workflow.

## Things to watch out for

- **Commit noise**: every 6 hours = ~28 commits/week on
  `update-time-log`. That's fine for a data-log branch but don't merge
  it into `main`. Keep `update-time-log` as a dedicated log branch.
- **Partial failures**: the script currently does *all* fetches before
  writing the CSV row. If any one of the four endpoints 403s/500s,
  nothing is logged for that run. That's the right behavior — don't
  "fix" it to write partial rows; a gap in the log is more honest than
  a row with empty columns.
- **Push races**: unlikely with a 6-hour cadence, but the `concurrency`
  key prevents overlap and a `git pull --rebase` before `git push`
  would handle the case where someone pushed manually between checkout
  and push. Keep it simple — start with just `concurrency`, add rebase
  only if pushes actually fail.
- **Secrets**: this workflow does *not* need `DISCORD_WEBHOOK_URL`.
  Only the weekly-post workflow needs it.
- **Don't touch `main`**: the workflow must only push to
  `update-time-log`.

## Rough file sketch

```yaml
name: Poll CDC Update Times

on:
  schedule:
    - cron: "0 */6 * * *"
  workflow_dispatch:

concurrency:
  group: poll-update-times
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  poll:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with:
          ref: update-time-log

      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"

      - name: Poll CDC endpoints
        run: python check_update_times.py

      - name: Commit and push
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add update_log.csv
          git diff --cached --quiet && echo "No changes" && exit 0
          git commit -m "chore: poll CDC update times"
          git push origin update-time-log
```

(Exact YAML to be refined on your laptop — this is a starting point.)

## After it's running

- Let it collect a week or two of data.
- Eyeball `update_log.csv` to find the earliest each dataset reliably
  updates. Compare to the current Friday 16:00 UTC schedule in
  `weekly-post.yml`.
- Adjust the weekly post's cron (or leave it) based on what you learn.
- Once you've got enough data to decide, consider whether the polling
  workflow should keep running forever or be disabled. (It's cheap —
  probably fine to leave on.)
