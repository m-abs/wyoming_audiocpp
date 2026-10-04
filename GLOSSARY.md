# Wyoming audio.cpp Bridges

Bridges that translate the Wyoming voice protocol into audio.cpp's OpenAI-compatible HTTP API, for use with Home Assistant.

## Language

**Bridge**:
A Wyoming TCP service that accumulates voice events from a client and relays them to the audio.cpp backend over HTTP. Each bridge speaks one direction of the speech pipeline: ASR (speech → text) or TTS (text → speech).
_Avoid_: adapter, connector, proxy

**audio.cpp backend**:
The separate model-serving HTTP service that the bridges call. It exposes an OpenAI-compatible API (`/v1/audio/transcriptions`, `/v1/audio/speech`) and is not itself a Wyoming service. The bridges are its only clients in this project.
_Avoid_: model server, inference server

**Wyoming protocol**:
The TCP event protocol used by Home Assistant voice assistants to communicate with speech services. Events are framed as `{"type": ..., "data_length": N}` headers followed by raw data bytes. The bridges implement the ASR and TTS variants of this protocol.
_Avoid_: Wyoming API, voice protocol
