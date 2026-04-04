"""Support for Volcengine TTS service."""

import asyncio
import uuid
from logging import Logger
from typing import Any, AsyncGenerator, Mapping

import voluptuous
from homeassistant.components.tts import (TextToSpeechEntity, TTSAudioRequest,
                                          TTSAudioResponse, Voice)
from homeassistant.config_entries import (ConfigEntry, ConfigSubentryFlow,
                                          SubentryFlowResult)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import \
    AddConfigEntryEntitiesCallback
from homeassistant.helpers.selector import (SelectSelector,
                                            SelectSelectorConfig,
                                            SelectSelectorMode)

from custom_components.volcengine_voice_assistant import LOGGER, gen_unique_id
from custom_components.volcengine_voice_assistant.sdk.tts import Client

VOICE_MAP: Mapping[str, Mapping[str, list[Voice]]] = {
    "seed-tts-2.0": {
        "zh-CN": {
            Voice(voice_id="zh_female_vv_uranus_bigtts", name="Vivi 2.0"),
            Voice(voice_id="zh_female_xiaohe_uranus_bigtts", name="小何 2.0"),
            Voice(voice_id="zh_male_m191_uranus_bigtts", name="云舟 2.0"),
            Voice(voice_id="zh_male_taocheng_uranus_bigtts", name="小天 2.0"),
            Voice(voice_id="zh_male_liufei_uranus_bigtts", name="刘飞 2.0")
        },
        "en-US": {
            Voice(voice_id="zh_female_vv_uranus_bigtts", name="Vivi 2.0"),
            Voice(voice_id="zh_female_xiaohe_uranus_bigtts", name="小何 2.0"),
            Voice(voice_id="zh_male_m191_uranus_bigtts", name="云舟 2.0"),
            Voice(voice_id="zh_male_taocheng_uranus_bigtts", name="小天 2.0"),
            Voice(voice_id="zh_male_liufei_uranus_bigtts", name="刘飞 2.0")
        },
        "ja-JP": {
            Voice(voice_id="zh_female_vv_uranus_bigtts", name="Vivi 2.0")
        },
        "id-ID": {
            Voice(voice_id="zh_female_vv_uranus_bigtts", name="Vivi 2.0")
        },
        "es-MX": {
            Voice(voice_id="zh_female_vv_uranus_bigtts", name="Vivi 2.0")
        }
    }
}


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
                    options=list(VOICE_MAP.keys()),
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
                        "wss://openspeech.bytedance.com/api/v3/tts/unidirectional/stream",
                        "wss://openspeech.bytedance.com/api/v3/tts/bidirection",
                        "wss://openspeech.bytedance.com/api/v3/tts/unidirectional/stream"
                    ],
                    mode=SelectSelectorMode.DROPDOWN
                )
            ),
            voluptuous.Required("resource_id"): SelectSelector(
                SelectSelectorConfig(
                    options=list(VOICE_MAP.keys()),
                    mode=SelectSelectorMode.DROPDOWN
                )
            ),
            voluptuous.Required("app_key"): str,
            voluptuous.Required("access_key"): str,
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
            async with Client(self.__logger, user_input["url"], user_input["app_key"], user_input["access_key"], user_input["resource_id"]) as client:
                await client.async_connect()
                await client.async_disconnect()
        except Exception as e:
            self.__logger.error(
                f"Invalid user input: {user_input}, error: {e}")
            return False

        return True


class Provider(TextToSpeechEntity):

    _attr_name: str = ""
    _attr_unique_id: str = ""
    _attr_default_language: str = "zh-CN"
    _attr_default_options: Mapping[str, Any] = {
        "voice": "zh_female_vv_uranus_bigtts"}
    _attr_supported_languages: list[str] = [
        "zh-CN", "en-US", "ja-JP", "id-ID", "es-MX"]
    _attr_supported_options: list[str] = ["voice"]

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

        self.__logger = LOGGER.getChild(self.unique_id)
        self.__url = url
        self.__app_key = app_key
        self.__access_key = access_key
        self.__resource_id = resource_id

    @callback
    def async_get_supported_voices(self, language: str) -> list[Voice]:
        """Return a list of supported voices for a language."""
        return VOICE_MAP.get(self.__resource_id, {}).get(language, None)

    async def async_stream_tts_audio(self, request: TTSAudioRequest) -> TTSAudioResponse:
        return TTSAudioResponse(self.__encoding,  self.__async_stream_tts_audio(request))

    async def __async_stream_tts_audio(self, request: TTSAudioRequest) -> AsyncGenerator[bytes]:
        async with Client(self.__logger, self.__url, self.__app_key, self.__access_key, self.__resource_id) as client:
            await client.async_connect()
            try:
                self.__logger.error(f"request: {request}")
                await client.async_start_session(
                    str(uuid.uuid4()), request.options.get("voice", ""),
                    self.__encoding, self.__sample_rate, self.__enable_timestamp, self.__disable_markdown_filter)

                async def sender():
                    try:
                        async for text in request.message_gen:
                            await client.async_send_task(text)
                    except Exception as e:
                        self.__logger.error(f"sender text failed: {e}")
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
                    self.__logger.error(f"Failed to recv audio: {e}")

                    try:
                        sender_task.cancel()
                        await sender_task
                        self.__logger.info(
                            "Sender task cancelled successfully")
                    except asyncio.CancelledError:
                        self.__logger.info("Sender task was already cancelled")
                        pass

                    raise
            except Exception as e:
                self.__logger.error(f"TSS failed: {e}")
            finally:
                await client.async_disconnect()
