# Base: Python runtime + shared deps
FROM python:3.14-slim AS base
WORKDIR /app

# Shared dependencies (cached layer)
COPY pyproject.toml ./
COPY wyoming_audiocpp_tts/pyproject.toml ./wyoming_audiocpp_tts/
RUN pip install --no-cache-dir "wyoming>=1.10.2,<2" "requests>=2.31,<3"

# Default config baked into the image
COPY config.example.json /config/config.json

# ASR target
FROM base AS asr
COPY . .
RUN pip install --no-cache-dir .
EXPOSE 11301
CMD ["python", "-m", "wyoming_audiocpp_asr", "--config", "/config/config.json"]

# TTS target
FROM base AS tts
COPY . .
RUN pip install --no-cache-dir ./wyoming_audiocpp_tts
EXPOSE 11201
CMD ["python", "-m", "wyoming_audiocpp_tts", "--config", "/config/config.json"]
