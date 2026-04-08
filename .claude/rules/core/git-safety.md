# Git Safety

> Supplement Claude Code's built-in safety with project-specific guidance.

## Preferred Safe Alternatives

| Destructive Command | Prefer Instead |
|---------------------|----------------|
| `git reset --hard` | `git stash push -m "backup"` |
| `git clean -f` | `git stash -u` |
| `git push --force` | `git push --force-with-lease` |
| `git checkout .` / `git restore .` | `git stash` (preserves changes) |

When the user requests a destructive git operation:
1. Suggest the safer alternative above
2. If they confirm the destructive version, proceed — they've been informed

**Hard block**: Never force-push to `main` or `master` without explicit user confirmation that they understand the risk to shared history.

## Commit Hygiene

- **Stage before commit**: Always `git add` all intended files before `git commit`. Never leave tracked changes unstaged — pre-commit stashes them, causing hook failures and re-commit cycles.
- **Stage specifically**: Use explicit file paths (`git add file1 file2`), not `git add -A` or `git add .`, to avoid accidentally staging secrets or binaries.
