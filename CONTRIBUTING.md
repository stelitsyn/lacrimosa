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

## What we're looking for

- **Bug fixes** — broken config paths, logic errors, test failures
- **Genericization gaps** — any remaining hardcoded values that should
  come from `config.yaml`
- **Documentation** — clearer setup instructions, missing context
- **New sensors** — additional data sources for the discovery specialist
- **New skills** — workflow recipes for specialist use

## What we're not looking for

- Support for AI providers other than Claude Code (architectural decision)
- Major architectural rewrites without discussion
- Changes that break config.yaml backward compatibility

## Code standards

- Python 3.11+, type hints where practical
- Tests with pytest — run `./run_all_tests.sh` before submitting
- Max 300 lines per file, 30 lines per function
- No hardcoded product-specific values — everything through `config.yaml`

## License

By contributing, you agree that your contributions will be licensed
under the same [non-commercial license](LICENSE) as the project.
The `schema-mcp/` component uses [MIT](schema-mcp/LICENSE).
