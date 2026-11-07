"""Static configuration"""

from typing import Mapping

from homeassistant.components.tts import Voice

VALID_LANGUAGES: Mapping[str, list[str]] = {
    "volc.bigasr.sauc.duration": ["zh-CN", "en-US", "ja-JP", "id-ID", "es-MX", "pt-BR", "de-DE", "fr-FR", "ko-KR", "fil-PH", "ms-MY", "th-TH", "ar-SA", "it-IT", "bn-BD", "el-GR", "nl-NL", "ru-RU", "tr-TR", "vi-VN", "pl-PL", "ro-RO", "ne-NP", "uk-UA", "yue-CN"],
    "volc.bigasr.sauc.concurrent": ["zh-CN", "en-US", "ja-JP", "id-ID", "es-MX", "pt-BR", "de-DE", "fr-FR", "ko-KR", "fil-PH", "ms-MY", "th-TH", "ar-SA", "it-IT", "bn-BD", "el-GR", "nl-NL", "ru-RU", "tr-TR", "vi-VN", "pl-PL", "ro-RO", "ne-NP", "uk-UA", "yue-CN"],
    "volc.seedasr.sauc.duration": ["zh-CN", "en-US", "ja-JP", "id-ID", "es-MX", "pt-BR", "de-DE", "fr-FR", "ko-KR", "fil-PH", "ms-MY", "th-TH", "ar-SA", "it-IT", "bn-BD", "el-GR", "nl-NL", "ru-RU", "tr-TR", "vi-VN", "pl-PL", "ro-RO", "ne-NP", "uk-UA", "yue-CN"],
    "volc.seedasr.sauc.concurrent": ["zh-CN", "en-US", "ja-JP", "id-ID", "es-MX", "pt-BR", "de-DE", "fr-FR", "ko-KR", "fil-PH", "ms-MY", "th-TH", "ar-SA", "it-IT", "bn-BD", "el-GR", "nl-NL", "ru-RU", "tr-TR", "vi-VN", "pl-PL", "ro-RO", "ne-NP", "uk-UA", "yue-CN"]
}

DEFAULT_VOICES: Mapping[str, str] = {
    "seed-tts-2.0": "zh_female_vv_uranus_bigtts",
    "seed-tts-1.0": "zh_female_vv_mars_bigtts",
    "seed-tts-1.0-concurr": "zh_female_vv_mars_bigtts"
}

# VALID_VOICES_START
VALID_VOICES: Mapping[str, Mapping[str, list[Voice]]] = {
}
# VALID_VOICES_END
