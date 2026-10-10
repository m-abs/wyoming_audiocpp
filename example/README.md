# Docker Compose Example

A full local voice stack: audio.cpp (models) plus the two Wyoming bridges that
Home Assistant connects to.

```
example/
├── docker-compose.yml   # audiocpp + asr + tts
├── server.json          # audio.cpp model config
├── config.json          # bridge config (shared by both bridges)
└── models/              # GGUF model packages (not committed)
```

## 1. Download the models

The compose file mounts `./models` at `/app/models` inside the audio.cpp
container, so `server.json` can reference the model packages by that path.

```bash
hf download audio-cpp/audio.cpp-gguf OmniVoice-GGUF Hviske-v5.3-GGUF --local-dir ./models
```

(`hf` is the Hugging Face CLI: `pip install huggingface_hub`. The files are
~1.35 GB and ~2.4 GB.) The result:

```
models/
├── OmniVoice-GGUF/
│   └── omnivoice-q8_0.gguf
└── Hviske-v5.3-GGUF/
    └── hviske-v5.3-q8_0.gguf
```

## 2. Point `server.json` at them

`server.json` declares the models audio.cpp serves. Each entry needs an `id`
(the name the bridges send in the request), a `family`, and a `path` under
`/app/models`:

```json
{
  "host": "0.0.0.0",
  "port": 8080,
  "backend": "cuda",
  "device": 0,
  "lazy_load": true,
  "max_loaded_models": 1,
  "models": [
    {
      "id": "omnivoice",
      "family": "omnivoice",
      "path": "/app/models/OmniVoice-GGUF",
      "task": "tts",
      "mode": "offline",
      "default_request_options": { "instruct": "female, low pitch", "speed": 1.0 }
    },
    {
      "id": "hviske",
      "family": "hviske_asr",
      "path": "/app/models/Hviske-v5.3-GGUF",
      "task": "asr",
      "mode": "offline"
    }
  ]
}
```

- `path` may be a directory (audio.cpp resolves the GGUF package inside it) or a
  direct `.gguf` file path.
- `lazy_load: true` registers the ids at startup and loads each model on its
  first request; `max_loaded_models: 1` keeps one model resident, which matters
  when both TTS and ASR run on the same GPU.
- `default_request_options` are applied by audio.cpp when a request does not
  supply them; the bridges forward `options` from `config.json`.
- No GPU: set `"backend": "cpu"` and use the `full-cpu` image (see the comment
  in `docker-compose.yml`).

## 3. Configure the bridges

`config.json` is the single config both bridge containers read (mounted at
`/config/config.json`). `audiocpp_uri` uses the compose service name
`audiocpp`, not `localhost`. The `id` of each model in `server.json` must match
`asr_model` and the voices' `model` in `config.json`.

## 4. Run

```bash
docker compose up -d
docker compose ps                 # audiocpp should be healthy
curl http://localhost:8080/health
```

Smoke-test the endpoints directly:

```bash
# TTS
curl -s -X POST http://localhost:8080/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"model":"omnivoice","input":"Hej, det er audio.cpp.","language":"da"}' \
  -o speech.wav

# ASR (any 16 kHz mono WAV; test_data/ has samples)
curl -s -X POST http://localhost:8080/v1/audio/transcriptions \
  -F model=hviske -F file=@../test_data/RMHL20190028_000013.wav
```

## 5. Connect Home Assistant

In Home Assistant, add the **Wyoming Protocol** integration twice — once per
bridge — with the host and port of each container:

| Service        | Host          | Port   |
| -------------- | ------------- | ------ |
| ASR bridge     | `<host>`      | `11301` |
| TTS bridge     | `<host>`      | `11201` |

If Home Assistant runs on the same machine, use the published ports above.
`enable_zeroconf` in `config.json` registers the services via mDNS
(`_wyoming._tcp.local.`) so Home Assistant can discover them, but mDNS from
inside a container is often not reachable from the host — leave it `false`
unless you have verified discovery works in your setup.
