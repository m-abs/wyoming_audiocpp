#!/bin/bash
 cd /workspaces/wyoming_audiocpp_demo
/workspaces/.venv/bin/python -m wyoming_audiocpp_tts --host 127.0.0.1 --port 11201 --tts-voice0-model omnivoice --tts-voice0-name TestVoice --tts-voice0-language da >/dev/null 2>&1 &
TTS_PID=$!
/workspaces/.venv/bin/python -m wyoming_audiocpp_asr --host 127.0.0.1 --port 11301 --model hviske >/dev/null 2>&1 &
ASR_PID=$!
sleep 4
echo "TTS:$(curl -s --noproxy '*' http://127.0.0.1:11201/ | head -c 120)"
echo "ASR info:$(curl -s --noproxy '*' http://127.0.0.1:11301/api/info | head -c 120)"
echo "ASR models:$(curl -s --noproxy '*' http://127.0.0.1:11301/models | head -c 200)"
# Test the real TTS path with the bridge pointing at audio.cpp
echo "=== TTS bridge at audio.cpp ==="
TTS2=/workspaces/.venv/bin/python -m wyoming_audiocpp_tts --host 127.0.0.1 --port 11202 --tts-voice0-model omnivoice --tts-voice0-name TestVoice --tts-voice0-language da --audiocpp-uri http://audio.cpp:8080 >/dev/null 2>&1 &
sleep 3
curl -s --noproxy '*' -X POST http://127.0.0.1:11202/api/tts -H "Content-Type: application/json" -d '{"text":"hej"}' | head -c 8
echo " <- is RIFF (WAV) if TTS works"
