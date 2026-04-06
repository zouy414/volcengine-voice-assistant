"""Support for Volcengine TTS service."""

import asyncio
import uuid
from logging import Logger
from typing import Any, AsyncGenerator, Mapping

import voluptuous
from homeassistant.components.tts import (TextToSpeechEntity, TTSAudioRequest,
                                          TTSAudioResponse, TtsAudioType,
                                          Voice)
from homeassistant.config_entries import (ConfigEntry, ConfigSubentryFlow,
                                          SubentryFlowResult)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import \
    AddConfigEntryEntitiesCallback
from homeassistant.helpers.selector import (SelectSelector,
                                            SelectSelectorConfig,
                                            SelectSelectorMode)

from . import LOGGER, gen_unique_id
from .config import DEFAULT_VOICES, VALID_VOICES
from .sdk.tts import Client


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
            LOGGER.exception("Setup %s failed: %s", subentry.data["name"], e)
            raise


class SubentryFlow(ConfigSubentryFlow):
    """Handle subentry flow for adding and modifying a location."""
    USER_DATA_SCHEMA = voluptuous.Schema(
        {
            voluptuous.Required("name", default="Volcengine TTS Service", ): str,
            voluptuous.Required("url", default="wss://openspeech.bytedance.com/api/v3/tts/bidirection"): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        "wss://openspeech.bytedance.com/api/v3/tts/bidirection",
                        "wss://openspeech.bytedance.com/api/v3/tts/unidirectional/stream"
                    ],
                    mode=SelectSelectorMode.DROPDOWN
                )
            ),
            voluptuous.Required("resource_id"): SelectSelector(
                SelectSelectorConfig(
                    options=list(VALID_VOICES.keys()),
                    mode=SelectSelectorMode.DROPDOWN
                )
            ),
            voluptuous.Required("app_key"): str,
            voluptuous.Required("access_key"): str,
        }
    )
    RECONFIGURE_DATA_SCHEMA = voluptuous.Schema(
        {
            voluptuous.Required("url", default="wss://openspeech.bytedance.com/api/v3/tts/bidirection"): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        "wss://openspeech.bytedance.com/api/v3/tts/bidirection",
                        "wss://openspeech.bytedance.com/api/v3/tts/unidirectional/stream"
                    ],
                    mode=SelectSelectorMode.DROPDOWN
                )
            ),
            voluptuous.Required("resource_id"): SelectSelector(
                SelectSelectorConfig(
                    options=list(VALID_VOICES.keys()),
                    mode=SelectSelectorMode.DROPDOWN
                )
            ),
            voluptuous.Required("app_key"): str,
            voluptuous.Required("access_key"): str,
        }
    )

    __logger: Logger = LOGGER.getChild(__qualname__)

    async def async_step_user(self, user_input: dict[str, Any]) -> SubentryFlowResult:
        """User flow to add a new location."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=self.USER_DATA_SCHEMA)

        if not await self.__is_valid_user_input(user_input):
            return self.async_abort(reason="Can not connect to server")

        return self.async_create_entry(title=user_input["name"], data=user_input, unique_id=gen_unique_id(user_input["name"]))

    async def async_step_reconfigure(self, user_input: dict[str, Any]) -> SubentryFlowResult:
        """User flow to modify an existing location."""
        if user_input is None:
            suggested_values = dict(self._get_reconfigure_subentry().data)
            del suggested_values['access_key']
            return self.async_show_form(step_id="reconfigure", data_schema=self.add_suggested_values_to_schema(self.RECONFIGURE_DATA_SCHEMA, suggested_values))

        error: str = await self.__is_valid_user_input(user_input)
        if error:
            return self.async_abort(reason=error)

        return self.async_update_and_abort(self._get_entry(), self._get_reconfigure_subentry(), data_updates=user_input)

    async def __is_valid_user_input(self, user_input: dict[str, Any]) -> str:
        try:
            async with Client(user_input["url"], user_input["app_key"], user_input["access_key"], user_input["resource_id"]) as client:
                await client.async_connect()
                await client.async_disconnect()
            return None
        except Exception as e:
            del user_input["access_key"]
            self.__logger.exception(
                f"Invalid user input: {user_input}, error: {e}")
            return f"{e}"


class Provider(TextToSpeechEntity):
    """TextToSpeech provider"""
    _attr_name: str = ""
    _attr_unique_id: str = ""
    _attr_default_language: str = "zh-CN"
    _attr_default_options: Mapping[str, Any]
    _attr_supported_languages: list[str] = []
    _attr_supported_options: list[str] = []

    __logger: Logger
    __url: str
    __app_key: str
    __access_key: str
    __resource_id: str
    __encoding: str = "mp3"
    __sample_rate: int = 24000
    __enable_timestamp: bool = True
    __disable_markdown_filter: bool = False

    def __init__(self, name: str, url: str, app_key: str, access_key: str, resource_id: str):
        self._attr_name = name
        self._attr_unique_id = gen_unique_id(name)
        self._attr_default_options = {"voice": DEFAULT_VOICES.get(resource_id)}
        self._attr_supported_languages = list(
            VALID_VOICES.get(resource_id).keys())
        self._attr_supported_options: list[str] = ["voice"]

        self.__logger = LOGGER.getChild(self.unique_id)
        self.__url = url
        self.__app_key = app_key
        self.__access_key = access_key
        self.__resource_id = resource_id

    @callback
    def async_get_supported_voices(self, language: str) -> list[Voice]:
        return VALID_VOICES.get(self.__resource_id).get(language)

    def get_tts_audio(self, message: str, language: str, options: dict[str, Any]) -> TtsAudioType:
        return asyncio.run(self.async_get_tts_audio(message, language, options))

    async def async_stream_tts_audio(self, request: TTSAudioRequest) -> TTSAudioResponse:
        return TTSAudioResponse(self.__encoding,  self.__async_stream_tts_audio(request))

    async def __async_stream_tts_audio(self, request: TTSAudioRequest) -> AsyncGenerator[bytes]:
        async with Client(self.__url, self.__app_key, self.__access_key, self.__resource_id) as client:
            resp = await client.async_connect()
            self.__logger.info(f"Connect successfully, response: {resp}")

            try:
                resp = await client.async_start_session(
                    str(uuid.uuid4()), request.options.get("voice"),
                    self.__encoding, self.__sample_rate, self.__enable_timestamp, self.__disable_markdown_filter)
                self.__logger.info(
                    f"Start session successfully, response: {resp}")

                async def sender():
                    try:
                        async for text in request.message_gen:
                            await client.async_send_task(text)
                    except Exception as e:
                        self.__logger.exception(f"Send text failed: {e}")
                        raise
                    finally:
                        await client.async_finish_session()

                # Start sending characters in background
                sender_task = asyncio.create_task(sender())

                # Collect responses from the server
                try:
                    async for resp in client.async_recv():
                        yield resp.payload
                except Exception as e:
                    self.__logger.exception(f"Failed to process request: {e}")

                    try:
                        sender_task.cancel()
                        await sender_task
                        self.__logger.info(
                            "Sender task cancelled successfully")
                    except asyncio.CancelledError:
                        pass

                    raise
            except Exception as e:
                self.__logger.exception(f"Text to speech failed: {e}")
            finally:
                await client.async_disconnect()
