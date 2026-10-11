# Docker RC tagging fix (2026-10-11)

## Symptom

`Docker` workflow run #13 (push to `rc` @ `4bfc40b`) failed in step
"Read version and check publish eligibility" with curl exit code 22 (HTTP
error, `-f`), so no image was published and no git tag was created.

## Root cause

The RC number and the "already published" check were derived from the ghcr
registry metadata API:

```
curl -sf -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://ghcr.io/v2/m-abs/wyoming_audiocpp/asr/tags/list
```

`ghcr.io/v2/.../tags/list` is not anonymous-accessible (401 for both existing
and non-existent package names), and the default Actions `GITHUB_TOKEN` does
not reliably grant registry read on the owner's packages. Any non-2xx response
makes `curl -f` exit 22, and `set -euo pipefail` aborts the step.

## Fix

Use git tags as the release ledger instead of the registry API
(`.github/workflows/docker.yml`):

- `Checkout` now uses `fetch-depth: 0`, so all tags are present.
- On `rc`: if a tag exactly equal to the base version exists (`git tag -l
  "0.2.1"`), the base is already released → `publish=false`.
- Otherwise the RC number is `max(existing <base>-rcN) + 1`
  (`git tag -l "0.2.1-rc*" | sed 's/.*-rc//' | sort -n | tail -1`).
- The "Create git tag" step is idempotent: it skips if the tag already exists,
  so a re-run after a failed build does not error on `git tag`.

Tags are only created after a successful image push, so they stay in sync with
what is actually on ghcr.io.

## Verification

Logic exercised locally against the real repo tags (`0.1.0-rc1`, `0.2.0`,
`0.2.0-rc1`, `0.2.1-rc1`) and `pyproject.toml` version `0.2.1`:

| base | ref | result |
|---|---|---|
| `0.2.1` | `rc` | publish `0.2.1-rc2` |
| `0.2.0` | `rc` | skip (tag `0.2.0` exists) |
| `0.3.0` | `rc` | publish `0.3.0-rc1` |
| any | `main` | publish base version |

Workflow YAML parses cleanly. Next push to `rc` publishes `0.2.1-rc2` and tags
it.
