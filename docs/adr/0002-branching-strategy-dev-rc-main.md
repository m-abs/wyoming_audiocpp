# Branching strategy: dev / rc / main

Docker images are published to `ghcr.io/m-abs/wyoming_audiocpp/{asr,tts}` via GitHub Actions. Three branches govern the release flow: `dev` (feature development), `rc` (release candidates), `main` (stable releases). Merging `dev` → `rc` triggers a RC build (e.g. `0.1.0-rc1`). Merging `rc` → `main` triggers a release build (e.g. `0.1.0`, tagged `latest`). The version is bumped manually in `pyproject.toml` as part of the release PR; CI reads it from there. No direct push to `main` — all changes go through a PR.

**Considered options:** Main-only with tag-based releases (rejected: no RC testing window); auto-bump on merge (rejected: loses control over semver major/minor/patch choice).

**Consequences:** After a release, the next RC cycle starts fresh from `dev` with the next version already bumped. No rc-branch sync step is needed.
