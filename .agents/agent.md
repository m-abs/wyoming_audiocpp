# Agent

## Python Environment

During development ALL python commands run inside the project's virtualenv at `.venv` (located in this repo root, next to `pyproject.toml`). Use it directly instead of any system interpreter so installed packages (`wyoming`, `flask`, …) are picked up:

- Invoke explicitly rather than relying on an activated shell PATH:
  - Python interpreter → `.venv/bin/python` (or `.venv/bin/python3.14`)
  - Package scripts such as tests/flask → run via that same python, e.g. `` .venv/bin/python … `` or with `-m`.
- Always launch from the repo root so `.venv/...` resolves to this project's environment and not a sibling one (e.g. `~/.bun`).

## Workspace Path

This repo is a devcontainer — when the working directory is `/workspaces` you are inside it (see `.devcontainer`). Mounts and tooling resolve relative to this path, so run python from here; do not assume anything outside or copy in.

This mirrors production: it is the interpreter the build uses, so keep running against it during dev too — never plain system python or an ambient global env unless deliberately testing outside the venv.

## Plans

First step efter approving a plan, the plan must be saved in `.agents/plans` and named `<DATE>_<NAME>.md`:

- Directory: `.agents/plans`
- Prefix: date (`YYYY-MM-DD`)
- Name: all uppercase, spaces replaced with `_`

Example: `.agents/plans/2026-09-27_WYOMING_AUDIOCPP_ASR_PLAN.md`.