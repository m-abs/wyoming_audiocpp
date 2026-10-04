# Containerization and Publishing Plan

Containerize the Wyoming audio.cpp bridges and publish Docker images to
`ghcr.io/m-abs/wyoming_audiocpp/{asr,tts}` via GitHub Actions.

## Design decisions

| Decision | Answer |
| --- | --- |
| Images | Separate ASR + TTS images, built from one Dockerfile at repo root (multi-stage, two targets) |
| Purpose | Deployment — long-lived services alongside audio.cpp |
| Config | `config.json` is primary; `WYO_AUDIOPCPP_URI` is optional env var override |
| Registry | `ghcr.io/m-abs/wyoming_audiocpp/asr`, `ghcr.io/m-abs/wyoming_audiocpp/tts` |
| Branching | `dev` → `rc` (RC build) → `main` (release build); no direct push to `main` |
| Version bump | Manual, in `pyproject.toml`, as part of the release PR |
| Semver flow | Standard — RC is pre-release of target version; main gets same version |
| Tags | No `v` prefix — git tags and Docker tags: `0.1.0`, `0.1.0-rc1` |

## What was done

### Docs

- **`GLOSSARY.md`** — Bridge, audio.cpp backend, Wyoming protocol.
- **`docs/adr/0001-shared-dockerfile-two-images.md`** — Multi-stage with two targets; why not separate Dockerfiles.
- **`docs/adr/0002-branching-strategy-dev-rc-main.md`** — RC flow, manual version bump, no direct push to main.
- **`docs/adr/0003-default-ports.md`** — Port changes (55001→11301, 10200→11201) and field rename (`uri` → `asr_uri`/`tts_uri`).
- **`docs/integration.md`** — Wyoming ↔ audio.cpp protocol details, event flows, wire format.
- **`README.md`** — Rewritten with 5-section structure: project description, integration with audio.cpp, ASR bridge, TTS bridge, Docker images, development.
- **`Dockerfile`** — Multi-stage: base (Python 3.14-slim + shared deps), `asr` target, `tts` target. Default config baked at `/config/config.json`.
- **`.github/workflows/docker.yml`** — Triggers on push to `rc`/`main`. Reads version from `pyproject.toml`. Builds and pushes both images to ghcr.io. `latest` tag only on `main`.
- **`config.example.json`** — Shared format with `asr_uri` + `tts_uri` (per-service bind URIs).

### Sidetrack fixes (ports + field rename)

- **Ports:** ASR 55001 → **11301**, TTS 10200 → **11201**.
- **Field rename:** `uri` → `asr_uri` / `tts_uri` in config.json, dataclass fields, CLI flags (`--asr-uri` / `--tts-uri`), env vars (`WYO_ASR_URI` / `WYO_TTS_URI`).
- Updated: `wyoming_audiocpp_asr/config.py`, `wyoming_audiocpp_tts/config.py`, both `__main__.py`, both `server.py`, tests, `.vscode/launch.json`, `.devcontainer/compose.yml`, `launch_real.py`, `AGENTS.md`, `README.md`.

### Verification

- 72 unit tests pass.
- Both Docker images build and run (ASR listens on 11301, TTS on 11201).

## Remaining work (user)

1. Create `dev`, `rc`, `main` branches in GitHub.
2. Set branch protection: no direct push to `main`, require PR.
3. Bump version in `pyproject.toml` to target release (e.g. `0.1.0`).
4. Merge `dev` → `rc` to trigger the first RC build.
5. Merge `rc` → `main` to publish the release.
