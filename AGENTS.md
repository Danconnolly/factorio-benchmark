# Repository Guidelines

## Project Structure & Module Organization

- `src/factorio_benchmark/` contains the installable Python package. Keep the
  evaluator independent of any live Factorio control transport.
- `scenarios/` holds versioned scenario manifests (for example,
  `smelt-one-iron-plate.v1.json`).
- `fixtures/` contains pinned baseline saves and their metadata; treat these as
  reproducibility artifacts, not generated scratch files.
- `tests/` contains `unittest` coverage for evaluator behavior and trace
  validation. `scripts/` contains narrowly scoped baseline-run helpers, and
  `docs/` records baseline provenance and verification status.

## Build, Test, and Development Commands

Use Python 3.12 or later. This project uses Hatchling for package builds and
has no mandatory formatter or linter configured.

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m build
```

The first command runs the complete test suite directly from the source tree.
The second builds distribution artifacts and may require the `build` package.
Run `python3 scripts/run_smelt_baseline.py --help` before using the baseline
runner; it operates on Factorio-specific inputs outside normal unit tests.

## Coding Style & Naming Conventions

Follow the existing Python style: four-space indentation, type annotations for
public-facing values, `snake_case` for functions and variables, and concise
module names. Prefer standard-library solutions and explicit validation errors.
Name tests `test_<behavior>` and keep scenario and fixture revisions explicit
with the `.vN.json` suffix. Preserve JSON field order and stable, readable
formatting when changing manifests or metadata.

## Testing Guidelines

Add a focused `unittest.TestCase` for every evaluator rule, including a passing
state and relevant rejection paths. Tests should use temporary files rather
than alter committed fixtures. Run the full discovery command above before
submitting changes. When a scenario, archive checksum, or baseline changes,
also update its metadata and the applicable documentation under `docs/`.

## Commit & Pull Request Guidelines

Use short imperative commit subjects consistent with the history, such as
`Add isolated smelting baseline runner` or `Verify first smelting baseline`.
Keep commits scoped to one logical change. Pull requests should state the
scenario/evaluator impact, list the tests run, and link related issues. Include
updated provenance or verification evidence for any pinned artifact change;
attach screenshots only when they clarify a user-visible Factorio workflow.
