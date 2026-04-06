# Volcengine Voice Assistant

[![CI](https://github.com/zouy414/volcengine-voice-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/zouy414/volcengine-voice-assistant/actions/workflows/ci.yml)
[![Release](https://github.com/zouy414/volcengine-voice-assistant/actions/workflows/release.yml/badge.svg)](https://github.com/zouy414/volcengine-voice-assistant/actions/workflows/release.yml)

A third-party custom component for Home Assistant to integrate Volcengine STT/TTS services.

## Quick Start

### Install

#### Via HACS

1. Go to `HACS`
2. Add Custom repository(Repository: https://github.com/zouy414/volcengine-voice-assistant, Type: Integration).
3. Search and install `Volcengine Voice Assistant`
4. Go to `Settings` -> `Devices & Services`
5. Click `Add Integration` button and add `Volcengine Voice Assistant`

#### Manually

1. Copy custom_components/volcengine_voice_assistant to `<home-assistant-config-directory>/custom_components`
2. Restart Home Assistant.
3. Go to `Settings` -> `Devices & Services`
4. Click `Add Integration` button and add `Volcengine Voice Assistant`

### Setup SpeechToText Service

1. Go to `Settings` -> `Devices & Services` -> `Volcengine Voice Assistant`.
2. Click `Add SpeechToText Service` button and fill out required field.
3. Click `Submit` button

### Setup TextToSpeech Service

1. Go to `Settings` -> `Devices & Services` -> `Volcengine Voice Assistant`.
2. Click `Add TextToSpeech Service` button and fill out required field.
3. Click `Submit` button
