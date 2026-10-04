FROM python:3.14-slim AS base
WORKDIR /app

# Install the full package (both bridges)
COPY pyproject.toml ./
COPY wyoming_audiocpp_common ./wyoming_audiocpp_common
RUN pip install --no-cache-dir ".[web,zeroconf]"

# Default config baked into the image
COPY config.docker.json /config/config.json

# ASR target
FROM base AS asr
EXPOSE 11301
COPY wyoming_audiocpp_asr ./wyoming_audiocpp_asr
CMD ["python", "-m", "wyoming_audiocpp_asr", "--config", "/config/config.json"]

# TTS target
FROM base AS tts
EXPOSE 11201
COPY wyoming_audiocpp_tts ./wyoming_audiocpp_tts
CMD ["python", "-m", "wyoming_audiocpp_tts", "--config", "/config/config.json"]
