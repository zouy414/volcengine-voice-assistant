"""Support for Volcengine TTS service."""

from logging import Logger
from typing import Any, Mapping

import voluptuous
from homeassistant.components.tts import (TextToSpeechEntity, TTSAudioRequest,
                                          TTSAudioResponse, TtsAudioType)
from homeassistant.config_entries import (ConfigEntry, ConfigSubentryFlow,
                                          SubentryFlowResult)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import \
    AddConfigEntryEntitiesCallback

from custom_components.volcengine_voice_assistant import LOGGER, gen_unique_id


async def async_setup_entry(_: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    """Setup tts provider"""

    for subentry in config_entry.subentries.values():
        try:
            if subentry.subentry_type != "tts":
                continue

            provider = Provider(subentry.data["name"], subentry.data["url"], subentry.data["app_key"],
                                subentry.data["access_key"], subentry.data["resource_id"])
            async_add_entities(
                [provider],
                config_subentry_id=subentry.subentry_id
            )
        except Exception as e:
            LOGGER.error(
                f"Setup {subentry.data["name"]} failed: {e}")
            raise


class SubentryFlow(ConfigSubentryFlow):
    USER_DATA_SCHEMA = voluptuous.Schema(
        {
            voluptuous.Required("name", default="Volcengine TTS Service", ): str,
            voluptuous.Required("url", default="wss://openspeech.bytedance.com/api/v3/tts/bidirection"): str,
            voluptuous.Required("app_key"): str,
            voluptuous.Required("access_key"): str,
            voluptuous.Required("resource_id", default="seed-tts-2.0"): str
        }
    )
    RECONFIGURE_DATA_SCHEMA = voluptuous.Schema(
        {
            voluptuous.Required("url", default="wss://openspeech.bytedance.com/api/v3/tts/bidirection"): str,
            voluptuous.Required("app_key"): str,
            voluptuous.Required("access_key"): str,
            voluptuous.Required("resource_id", default="seed-tts-2.0"): str
        }
    )

    __logger: Logger = LOGGER.getChild(__qualname__)

    async def async_step_user(self, user_input: dict[str, Any]) -> SubentryFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=self.USER_DATA_SCHEMA)

        if not await self.__is_valid_user_input(user_input):
            return self.async_abort(reason="Can not connect to server")

        return self.async_create_entry(title=user_input["name"], data=user_input, unique_id=gen_unique_id(user_input["name"]))

    async def async_step_reconfigure(self, user_input: dict[str, Any]) -> SubentryFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="reconfigure", data_schema=self.RECONFIGURE_DATA_SCHEMA)

        if not await self.__is_valid_user_input(user_input):
            return self.async_abort(reason="Can not connect to server")

        return self.async_update_and_abort(self._get_entry(), self._get_reconfigure_subentry(), data=user_input)

    async def __is_valid_user_input(self, user_input: dict[str, Any]) -> bool:
        try:
            pass
        except Exception as e:
            self.__logger.error(
                f"Invalid user input: {user_input}, error: {e}")
            return False

        return True


class Provider(TextToSpeechEntity):
    _attr_name: str = ""
    _attr_unique_id: str = ""

    __logger: Logger
    __url: str
    __app_key: str
    __access_key: str
    __resource_id: str

    def __init__(self, name: str, url: str, app_key: str, access_key: str, resource_id: str):
        self._attr_name = name
        self._attr_unique_id = gen_unique_id(name)

        self.__logger = LOGGER.getChild(self.unique_id)
        self.__url = url
        self.__app_key = app_key
        self.__access_key = access_key
        self.__resource_id = resource_id

    @property
    def supported_languages(self) -> list[str]:
        """Return a list of supported languages."""
        return self._attr_supported_languages

    @property
    def default_language(self) -> str:
        """Return the default language."""
        return self._attr_default_language

    @property
    def supported_options(self) -> list[str] | None:
        """Return a list of supported options like voice, emotions."""
        return self._attr_supported_options

    @property
    def default_options(self) -> Mapping[str, Any] | None:
        """Return a mapping with the default options."""
        return self._attr_default_options

    def get_tts_audio(self, message: str, language: str, options: dict[str, Any]) -> TtsAudioType:
        pass

    async def async_get_tts_audio(self, message: str, language: str, options: dict[str, Any]) -> TtsAudioType:
        pass

    async def async_stream_tts_audio(self, request: TTSAudioRequest) -> TTSAudioResponse:
        pass
