"""Support for Volcengine STT service."""

import asyncio
import logging
import voluptuous
from homeassistant.components.stt import (AsyncIterable, AudioBitRates,
                                          AudioChannels, AudioCodecs,
                                          AudioFormats, AudioSampleRates,
                                          SpeechMetadata, SpeechResult,
                                          SpeechResultState,
                                          SpeechToTextEntity)
from homeassistant.config_entries import ConfigEntry, ConfigSubentryFlow, SubentryFlowResult
from homeassistant.core import Any, HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from custom_components.volcengine_voice_assistant import DOMAIN
from custom_components.volcengine_voice_assistant.sdk.asr import Client


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback):
    """Setup stt provider"""

    for subentry in config_entry.subentries.values():
        if subentry.subentry_type != "stt":
            continue

        async_add_entities(Provider(
            logging.getLogger(subentry.data["name"]),
            subentry.data["url"],
            subentry.data["app_key"],
            subentry.data["access_key"],
            subentry.data["resource_id"]
        ))


class SubentryFlow(ConfigSubentryFlow):
    DATA_SCHEMA = voluptuous.Schema(
        {
            voluptuous.Required("name", default="Volcengine STT Service", description="The name of the STT service"): str,
            voluptuous.Required("url", default="wss://openspeech.bytedance.com/api/v3/sauc/bigmode", description="The URL of the STT service"): str,
            voluptuous.Required("app_key", description="The app key for the STT service"): str,
            voluptuous.Required("access_key", description="The access key for the STT service"): str,
            voluptuous.Required("resource_id", default="volc.seedasr.sauc.duration", description="The resource ID for the STT service"): str
        }
    )

    async def async_step_user(self, user_input: dict[str, Any]) -> SubentryFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=self.DATA_SCHEMA)

        if not await self.__is_valid_input(user_input):
            return self.async_abort(reason="Can not connect to server")

        return self.async_create_entry(title=user_input["name"], data=user_input)

    async def async_step_reconfigure(self, user_input: dict[str, Any]) -> SubentryFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="reconfigure", data_schema=self.add_suggested_values_to_schema(self.DATA_SCHEMA, self._get_reconfigure_subentry().data))

        if not await self.__is_valid_input(user_input):
            return self.async_abort(reason="Can not connect to server")

        return self.async_update_and_abort(self._get_entry(), self._get_reconfigure_subentry(), data=user_input)

    async def __is_valid_input(self, user_input: dict[str, Any]) -> bool:
        try:
            async with Client(user_input["url"], user_input["app_key"], user_input["access_key"], user_input["resource_id"]) as client:
                await client.connect(
                    user_input["name"],
                    audio_format=AudioFormats.WAV, audio_codec=AudioCodecs.PCM, audio_rate=AudioSampleRates.SAMPLERATE_16000, audio_bits=AudioBitRates.BITRATE_16, audio_channels=AudioChannels.CHANNEL_MONO
                )
                await client.disconnect()
        except Exception:
            return False

        return True


class Provider(SpeechToTextEntity):
    """Speech to text provider for Volcengine STT service."""

    __logger: logging.Logger
    __url: str
    __app_key: str
    __access_key: str
    __resource_id: str = "volc.bigasr.sauc.duration"

    def __init__(self, logger: logging.Logger, url: str, app_key: str, access_key: str, resource_id: str):
        self.__logger = logger
        self.__url = url
        self.__app_key = app_key
        self.__access_key = access_key
        self.__resource_id = resource_id

    @property
    def supported_languages(self) -> list[str]:
        return ["zh-CN"]

    @property
    def supported_formats(self) -> list[AudioFormats]:
        return [AudioFormats.WAV]

    @property
    def supported_codecs(self) -> list[AudioCodecs]:
        return [AudioCodecs.PCM]

    @property
    def supported_bit_rates(self) -> list[AudioBitRates]:
        return [AudioBitRates.BITRATE_16]

    @property
    def supported_sample_rates(self) -> list[AudioSampleRates]:
        return [AudioSampleRates.SAMPLERATE_16000]

    @property
    def supported_channels(self) -> list[AudioChannels]:
        return [AudioChannels.CHANNEL_MONO]

    async def async_process_audio_stream(self, metadata: SpeechMetadata, stream: AsyncIterable[bytes]) -> SpeechResult:
        async with Client(self.__url, self.__app_key, self.__access_key,  self.__resource_id) as client:
            # Connect to the server with the specified audio parameters
            await client.connect(
                self._attr_name,
                audio_format=metadata.format, audio_codec=metadata.codec, audio_rate=metadata.sample_rate, audio_bits=metadata.bit_rate, audio_channels=metadata.channel
            )

            # Start a separate task to send audio segments to the server
            async def sender():
                async for segment in stream:
                    client.send_segment(segment)
                await client.disconnect()
            sender_task = asyncio.create_task(sender())

            # Collect responses from the server and concatenate them into a single result string
            result: str = ""
            try:
                async for response in client.recv():
                    result += response.payload_msg

                return SpeechResult(result, SpeechResultState.SUCCESS)
            except Exception as e:
                self.__logger.error(f"Failed to process audio stream: {e}")

                try:
                    sender_task.cancel()
                    await sender_task
                    self.__logger.info(
                        "Sender task cancelled successfully")
                except asyncio.CancelledError:
                    self.__logger.info("Sender task was already cancelled")
                    pass

                return SpeechResult(result, SpeechResultState.ERROR)
