import asyncio
import logging

from homeassistant.components.stt import AsyncIterable, AudioBitRates, AudioChannels, AudioCodecs, AudioFormats, AudioSampleRates, SpeechMetadata, SpeechResult, SpeechResultState, SpeechToTextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.volcengine_voice_assistant.sdk.asr import Client


class SSTProvider(SpeechToTextEntity):
    __logger: logging.Logger
    __url: str = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel"
    __app_key: str
    __access_key: str
    __resource_id: str = "volc.bigasr.sauc.duration"
    _attr_name: str = "Volcengine STT Service"

    def __init__(self, logger: logging.Logger, hass: HomeAssistant, config_entry: ConfigEntry):
        self.__logger = logger.getChild("SSTProvider").setLevel(
            config_entry.options.get("log_level", logging.INFO))
        self.__url = config_entry.data.get("url", self.__url)
        self.__app_key = config_entry.data["app_key"]
        self.__access_key = config_entry.data["access_key"]
        self.__resource_id = config_entry.data["resource_id"]

    @property
    def supported_languages(self) -> list[str]:
        """Return a list of supported languages."""
        return ["zh-CN"]

    @property
    def supported_formats(self) -> list[AudioFormats]:
        """Return a list of supported formats."""
        return [AudioFormats.WAV]

    @property
    def supported_codecs(self) -> list[AudioCodecs]:
        """Return a list of supported codecs."""
        return [AudioCodecs.PCM]

    @property
    def supported_bit_rates(self) -> list[AudioBitRates]:
        """Return a list of supported bitrates."""
        return [AudioBitRates.BITRATE_16]

    @property
    def supported_sample_rates(self) -> list[AudioSampleRates]:
        """Return a list of supported samplerates."""
        return [AudioSampleRates.SAMPLERATE_16000]

    @property
    def supported_channels(self) -> list[AudioChannels]:
        """Return a list of supported channels."""
        return [AudioChannels.CHANNEL_MONO]

    async def async_process_audio_stream(self, metadata: SpeechMetadata, stream: AsyncIterable[bytes]) -> SpeechResult:
        """Process an audio stream to STT service.

        Only streaming content is allowed!
        """

        async with Client(self.__url, self.__app_key, self.__access_key,  self.__resource_id) as client:
            # Connect to the server with the specified audio parameters
            client.connect(
                self._attr_name,
                audio_format=metadata.format, audio_codec=metadata.codec, audio_rate=metadata.sample_rate, audio_bits=metadata.bit_rate, audio_channels=metadata.channel
            )

            # Start a separate task to send audio segments to the server
            async def sender():
                async for segment in stream:
                    client.send_segment(segment)
                client.disconnect()
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
