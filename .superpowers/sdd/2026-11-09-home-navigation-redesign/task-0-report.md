# Task 0: Packaging baseline fix

## Root cause

Hatchling's implicit VCS ignore handling did not exclude local files in this linked Git worktree: `.git` is a file pointing to the shared repository metadata, and the sdist included both the root `.worktrees/` tree and root `HANDOFF.md`. Source distribution exclusions were not explicitly configured.

## Files changed

- `pyproject.toml`: added explicit Hatchling sdist exclusions for the root `.worktrees` directory/tree and root `HANDOFF.md`.
- `.superpowers/sdd/2026-11-09-home-navigation-redesign/task-0-report.md`: this report.
- `tests/test_packaging.py` and `.gitignore` were not changed.

## Tests and exact results

- Before fix: `uv run pytest tests/test_packaging.py -q` — **2 failed**, both reproducing unwanted sdist members (`.worktrees/packaging-sentinel-*` and `HANDOFF.md`).
- After fix: `uv run pytest tests/test_packaging.py -q` — **2 passed in 1.36s**.
- After fix: `uv run pytest -q` — **103 passed in 2.44s**.
- `git diff --check` — **passed** (no output).

## Commit SHA

1e343cea2fbedc0c8d112a83b21ab0d485e6335a

## Self-review

The change is limited to the Hatchling sdist target and excludes root-anchored paths. The existing regression tests remain unchanged. No product behavior or dependencies changed.

## Concerns

None known.
