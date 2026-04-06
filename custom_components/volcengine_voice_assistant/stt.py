"""Support for Volcengine STT service."""

import asyncio
from logging import Logger

import voluptuous
from homeassistant.components.stt import (AsyncIterable, AudioBitRates,
                                          AudioChannels, AudioCodecs,
                                          AudioFormats, AudioSampleRates,
                                          SpeechMetadata, SpeechResult,
                                          SpeechResultState,
                                          SpeechToTextEntity)
from homeassistant.config_entries import (ConfigEntry, ConfigSubentryFlow,
                                          SubentryFlowResult)
from homeassistant.core import Any, HomeAssistant
from homeassistant.helpers.entity_platform import \
    AddConfigEntryEntitiesCallback
from homeassistant.helpers.selector import (SelectSelector,
                                            SelectSelectorConfig,
                                            SelectSelectorMode)

from . import LOGGER, gen_unique_id
from .sdk.asr import Client
from .sdk.utils import gen_wav_segment


async def async_setup_entry(_: HomeAssistant, config_entry: ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    """Setup stt provider"""

    for subentry in config_entry.subentries.values():
        try:
            if subentry.subentry_type != "stt":
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
            voluptuous.Required("name", default="Volcengine STT Service"): str,
            voluptuous.Required("url", default="wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel",
                        "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream",
                        "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
                    ],
                    mode=SelectSelectorMode.DROPDOWN
                )
            ),
            voluptuous.Required("resource_id", default="volc.seedasr.sauc.duration"): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        "volc.bigasr.sauc.duration",
                        "volc.bigasr.sauc.concurrent",
                        "volc.seedasr.sauc.duration",
                        "volc.seedasr.sauc.concurrent"
                    ],
                    mode=SelectSelectorMode.DROPDOWN
                )
            ),
            voluptuous.Required("app_key"): str,
            voluptuous.Required("access_key"): str,
        }
    )
    RECONFIGURE_DATA_SCHEMA = voluptuous.Schema(
        {
            voluptuous.Required("url", default="wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel",
                        "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream",
                        "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
                    ],
                    mode=SelectSelectorMode.DROPDOWN
                )
            ),
            voluptuous.Required("resource_id", default="volc.seedasr.sauc.duration"): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        "volc.bigasr.sauc.duration",
                        "volc.bigasr.sauc.concurrent",
                        "volc.seedasr.sauc.duration",
                        "volc.seedasr.sauc.concurrent"
                    ],
                    mode=SelectSelectorMode.DROPDOWN
                )
            ),
            voluptuous.Required("app_key"): str,
            voluptuous.Required("access_key"): str,
        }
    )

    __logger: Logger = LOGGER.getChild(__qualname__)

    async def async_step_user(
            self, user_input: dict[str, Any]) -> SubentryFlowResult:
        """User flow to add a new location."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=self.USER_DATA_SCHEMA)

        if not await self.__is_valid_user_input(user_input):
            return self.async_abort(reason="Can not connect to server")

        return self.async_create_entry(
            title=user_input["name"], data=user_input, unique_id=gen_unique_id(user_input["name"]))

    async def async_step_reconfigure(
            self, user_input: dict[str, Any]) -> SubentryFlowResult:
        """User flow to modify an existing location."""
        if user_input is None:
            suggested_values = dict(self._get_reconfigure_subentry().data)
            del suggested_values['access_key']
            return self.async_show_form(step_id="reconfigure", data_schema=self.add_suggested_values_to_schema(
                self.RECONFIGURE_DATA_SCHEMA, suggested_values))

        error: str = await self.__is_valid_user_input(user_input)
        if error:
            return self.async_abort(reason=error)

        return self.async_update_and_abort(
            self._get_entry(), self._get_reconfigure_subentry(), data_updates=user_input)

    async def __is_valid_user_input(self, user_input: dict[str, Any]) -> str:
        try:
            async with Client(user_input["url"], user_input["app_key"], user_input["access_key"], user_input["resource_id"]) as client:
                await client.async_connect(
                    user_input["name"], "zh-CN",
                    audio_format=AudioFormats.WAV, audio_codec=AudioCodecs.PCM, audio_rate=AudioSampleRates.SAMPLERATE_16000, audio_bits=AudioBitRates.BITRATE_16, audio_channels=AudioChannels.CHANNEL_MONO
                )
                await client.async_disconnect()
            return None
        except Exception as e:
            del user_input["access_key"]
            self.__logger.exception(
                "Invalid user input: %s, error: %s", user_input, e)
            return e


class Provider(SpeechToTextEntity):
    """Speech to text provider for Volcengine STT service."""

    _attr_name: str = ""
    _attr_unique_id: str = ""

    __logger: Logger
    __url: str
    __app_key: str
    __access_key: str
    __resource_id: str

    def __init__(self, name: str, url: str, app_key: str,
                 access_key: str, resource_id: str):
        self._attr_name = name
        self._attr_unique_id = gen_unique_id(name)

        self.__logger = LOGGER.getChild(self.unique_id)
        self.__url = url
        self.__app_key = app_key
        self.__access_key = access_key
        self.__resource_id = resource_id

    @property
    def supported_languages(self) -> list[str]:
        return ["zh-CN", "en-US", "ja-JP", "id-ID", "es-MX", "pt-BR", "de-DE", "fr-FR", "ko-KR", "fil-PH", "ms-MY", "th-TH",
                "ar-SA", "it-IT", "bn-BD", "el-GR", "nl-NL", "ru-RU", "tr-TR", "vi-VN", "pl-PL", "ro-RO", "ne-NP", "uk-UA", "yue-CN"]

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
        return [AudioChannels.CHANNEL_MONO, AudioChannels.CHANNEL_STEREO]

    async def async_process_audio_stream(
            self, metadata: SpeechMetadata, stream: AsyncIterable[bytes]) -> SpeechResult:
        self.__logger.info(f"Start speech to text, metadata: {metadata}")
        async with Client(self.__url, self.__app_key, self.__access_key, self.__resource_id) as client:
            # Connect to the server with the specified audio parameters
            resp = await client.async_connect(
                self._attr_name, metadata.language,
                audio_format=metadata.format, audio_codec=metadata.codec, audio_rate=metadata.sample_rate, audio_bits=metadata.bit_rate, audio_channels=metadata.channel
            )
            self.__logger.info("Connect successfully, response: %s", resp)

            try:
                # Start a separate task to send audio segments to the server
                async def async_sender():
                    try:
                        # NOTE: The segment from stream not include wav header
                        huge_segment: bytes = b""
                        async for segment in stream:
                            huge_segment += segment
                        await client.async_send_segment(gen_wav_segment(metadata.sample_rate, metadata.bit_rate, metadata.channel, huge_segment))
                    except Exception as e:
                        self.__logger.exception("Send segment failed: %s", e)
                        raise
                    finally:
                        await client.async_disconnect()
                sender_task = asyncio.create_task(async_sender())

                # Collect responses from the server and concatenate them into a
                # single result string
                result: str = ""
                try:
                    async for response in client.async_recv():
                        if not response.payload_msg:
                            self.__logger.debug(
                                "Recv not payload msg response: %s", response)
                            continue
                        result = response.payload_msg.get("result").get("text")

                    await sender_task

                    return SpeechResult(result, SpeechResultState.SUCCESS)
                except Exception as e:
                    self.__logger.exception("Failed to process stream: %s", e)

                    try:
                        sender_task.cancel()
                        await sender_task
                        self.__logger.info(
                            "Sender task cancelled successfully")
                    except asyncio.CancelledError:
                        pass

                    return SpeechResult(e, SpeechResultState.ERROR)
            except Exception as e:
                self.__logger.exception("Speech to text failed: %s", e)
