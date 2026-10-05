# Shared Dockerfile, two images

The project publishes two Docker images (ASR bridge and TTS bridge) to `ghcr.io`. Both packages share the same core dependencies (`wyoming`, `requests`) and a shared `config.json` format where each service ignores the fields it doesn't use. A single multi-stage Dockerfile at the repo root produces both images: a shared base stage installs the Python runtime and common deps, then two target stages (`asr`, `tts`) each install only their own package. Built with `docker build --target asr` / `--target tts`.

**Considered options:** Separate Dockerfiles per package (rejected: duplicated base setup, harder to keep consistent); single image with both packages and a runtime selector (rejected: each image carries the other service's code, larger images).
