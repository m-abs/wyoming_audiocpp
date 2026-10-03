#!/bin/bash
cd /workspaces/wyoming_audiocpp_demo
/workspaces/.venv/bin/python -m wyoming_audiocpp_tts --uri tcp://127.0.0.1:11201 --config /workspaces/config.example.json >/dev/null 2>&1 &
TTS_PID=$!
/workspaces/.venv/bin/python -m wyoming_audiocpp_asr --uri tcp://127.0.0.1:55301 --asr-web-server --asr-web-server-host 127.0.0.1 --asr-web-server-port 11301 --config /workspaces/config.example.json >/dev/null 2>&1 &
ASR_PID=$!
sleep 4
echo "TTS:$(curl -s --noproxy '*' http://127.0.0.1:11201/ | head -c 120)"
echo "ASR info:$(curl -s --noproxy '*' http://127.0.0.1:11301/api/info | head -c 120)"
echo "ASR health:$(curl -s --noproxy '*' http://127.0.0.1:11301/health)"
# Test the real TTS path with the bridge pointing at audio.cpp
echo "=== TTS bridge at audio.cpp ==="
TTS2=/workspaces/.venv/bin/python -m wyoming_audiocpp_tts --uri tcp://127.0.0.1:11202 --config /workspaces/config.example.json --audiocpp-uri http://audio.cpp:8080 >/dev/null 2>&1 &
sleep 3
curl -s --noproxy '*' -X POST http://127.0.0.1:11202/api/tts -H "Content-Type: application/json" -d '{"text":"hej"}' | head -c 8
echo " <- is RIFF (WAV) if TTS works"
