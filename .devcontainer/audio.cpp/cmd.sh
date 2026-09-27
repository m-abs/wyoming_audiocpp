#!/bin/bash

if [ -d /app/models/OmniVoice-GGUF ]; then
    python3 tools/model_manager_v2.py install omnivoice || echo
fi

if [ -d /app/models/Hviske-v5.3-GGUF ]; then
    python3 tools/model_manager_v2.py install hviske_asr || echo
fi

/app/entrypoint.sh server --config /app/server.json --ui --ui-management