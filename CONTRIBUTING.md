# Contributing to Lacrimosa

Lacrimosa was extracted from a production system. Rough edges from
that extraction are expected — leftover references, broken config
paths, logic mismatches. Fixes for these are especially welcome.

## How to contribute

1. Open an issue describing the problem or improvement
2. Fork the repo and create a branch
3. Make your changes
4. Run the test suite: `.venv/bin/pytest tests/ -v`
5. Submit a PR referencing the issue

All PRs require manual approval from the maintainer. There are no
auto-merge rules — every change is reviewed before it enters the repo.

## What we're looking for

- **Bug fixes** — broken config paths, logic errors, test failures
- **Genericization gaps** — any remaining hardcoded values that should
  come from `config.yaml`
- **Documentation** — clearer setup instructions, missing context
- **New sensors** — additional data sources for the discovery specialist
- **New skills** — workflow recipes for specialist use

## Larger changes — discuss first

- **Other AI providers** — welcome. Lacrimosa was built on Claude Code,
  but adapting it to other providers is a valid direction. Open an issue
  to discuss the approach before starting.
- **Architectural changes** — open an issue first so we can discuss the
  design. PRs with significant structural changes submitted without
  prior discussion are hard to review well.
- **Breaking config.yaml changes** — try to stay backward-compatible.
  If a breaking change is necessary, explain why in the PR.

## License

By contributing, you agree that your contributions will be licensed
under the same [non-commercial license](LICENSE) as the project.
The `schema-mcp/` component uses [MIT](schema-mcp/LICENSE).
