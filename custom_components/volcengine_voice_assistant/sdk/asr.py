"""Speech-to-Text SDK for Volcengine Voice Assistant

This model improve from the official demo code, and is designed to be more user-friendly and easier to integrate into applications.
It provides a simple interface for sending audio data and receiving transcriptions, while handling the underlying protocol details internally.
"""

import asyncio
import json
import struct
import uuid
from logging import Logger
from typing import Any, AsyncGenerator, Dict, Generator, List

from aiohttp import ClientSession, ClientWebSocketResponse, WSMsgType

from custom_components.volcengine_voice_assistant.sdk.utils import (
    gzip_compress, gzip_decompress, read_audio_file, read_wav_info)


class ProtocolVersion:
    V1 = 0b0001


class MessageType:
    CLIENT_FULL_REQUEST = 0b0001
    CLIENT_AUDIO_ONLY_REQUEST = 0b0010
    SERVER_FULL_RESPONSE = 0b1001
    SERVER_ERROR_RESPONSE = 0b1111


class MessageTypeSpecificFlags:
    NO_SEQUENCE = 0b0000
    POS_SEQUENCE = 0b0001
    NEG_SEQUENCE = 0b0010
    NEG_WITH_SEQUENCE = 0b0011


class SerializationType:
    NO_SERIALIZATION = 0b0000
    JSON = 0b0001


class CompressionType:
    GZIP = 0b0001


class Header:
    """Header for the streaming ASR protocol, containing metadata about the message type, serialization method, compression method, and other flags."""

    message_type: int
    message_type_specific_flags: int
    serialization_type: int
    compression_type: int
    reserved_data: bytes

    def __init__(self):
        self.message_type = MessageType.CLIENT_FULL_REQUEST
        self.message_type_specific_flags = MessageTypeSpecificFlags.POS_SEQUENCE
        self.serialization_type = SerializationType.JSON
        self.compression_type = CompressionType.GZIP
        self.reserved_data = bytes([0x00])

    def with_message_type(self, message_type: int) -> 'Header':
        self.message_type = message_type
        return self

    def with_message_type_specific_flags(self, flags: int) -> 'Header':
        self.message_type_specific_flags = flags
        return self

    def with_serialization_type(self, serialization_type: int) -> 'Header':
        self.serialization_type = serialization_type
        return self

    def with_compression_type(self, compression_type: int) -> 'Header':
        self.compression_type = compression_type
        return self

    def with_reserved_data(self, reserved_data: bytes) -> 'Header':
        self.reserved_data = reserved_data
        return self

    def to_bytes(self) -> bytes:
        """Convert the header to bytes format for transmission."""

        header = bytearray()
        header.append((ProtocolVersion.V1 << 4) | 1)
        header.append((self.message_type << 4) |
                      self.message_type_specific_flags)
        header.append((self.serialization_type << 4)
                      | self.compression_type)
        header.extend(self.reserved_data)
        return bytes(header)


class Request:
    header: Header
    payload_bytes: bytes
    is_last: bool = False

    def to_bytes(self, seq: int) -> bytes:
        """Convert the request to bytes format for transmission, with the given sequence number and whether it's the last package."""

        compressed_payload = gzip_compress(self.payload_bytes)

        request = bytearray()
        request.extend(self.header.to_bytes())
        request.extend(struct.pack('>i', -seq if self.is_last else seq))
        request.extend(struct.pack('>I', len(compressed_payload)))
        request.extend(compressed_payload)

        return bytes(request)


class ConnectRequest(Request):
    """Request for the streaming ASR protocol, containing the header and payload for a client request."""

    def __init__(self, uid: str, language: str,
                 audio_format: str = "wav", audio_codec: str = "raw", audio_rate: int = 16000, audio_bits: int = 16, audio_channels: int = 1,
                 model_name: str = "bigmodel", enable_itn: bool = True, enable_punc: bool = True, enable_ddc: bool = True, show_utterances: bool = True, enable_nonstream: bool = False):
        self.header = Header().with_message_type_specific_flags(
            MessageTypeSpecificFlags.POS_SEQUENCE)
        self.payload_bytes = json.dumps({
            "user": {
                "uid": uid
            },
            "audio": {
                "language": language,
                "format": audio_format,
                "codec": audio_codec,
                "rate": audio_rate,
                "bits": audio_bits,
                "channel": audio_channels
            },
            "request": {
                "model_name": model_name,
                "enable_itn": enable_itn,
                "enable_punc": enable_punc,
                "enable_ddc": enable_ddc,
                "show_utterances": show_utterances,
                "enable_nonstream": enable_nonstream
            }
        }).encode('utf-8')


class SegmentRequest(Request):
    def __init__(self, segment: bytes):
        self.header = Header().with_message_type_specific_flags(
            MessageTypeSpecificFlags.POS_SEQUENCE).with_message_type(MessageType.CLIENT_AUDIO_ONLY_REQUEST)
        self.payload_bytes = segment


class DisconnectRequest(Request):
    def __init__(self):
        self.header = Header().with_message_type_specific_flags(
            MessageTypeSpecificFlags.NEG_WITH_SEQUENCE).with_message_type(MessageType.CLIENT_AUDIO_ONLY_REQUEST)
        self.payload_bytes = bytes()
        self.is_last = True


class Stream:
    """Stream for the streaming ASR protocol, containing the audio data split into segments for transmission."""

    __segment_duration: int
    __segments: List[bytes]

    def __init__(self, content: bytes, segment_duration: int = 200):
        """Init stream from audio content in bytes."""

        segment_size = self.__get_segment_size(content, segment_duration)

        self.__segment_duration = segment_duration
        self.__segments = self.__split_audio(content, segment_size)

    @staticmethod
    def __get_segment_size(content: bytes, segment_duration: int) -> int:
        try:
            channel_num, samp_width, frame_rate, _, _ = read_wav_info(content)[
                :5]
            size_per_sec = channel_num * samp_width * frame_rate
            segment_size = size_per_sec * segment_duration // 1000
            return segment_size
        except Exception:
            raise

    @staticmethod
    def __split_audio(data: bytes, segment_size: int) -> List[bytes]:
        if segment_size <= 0:
            return []

        segments: List[bytes] = []
        for i in range(0, len(data), segment_size):
            end = i + segment_size
            if end > len(data):
                end = len(data)
            segments.append(data[i:end])

        return segments

    def read(self) -> Generator[bytes]:
        """Read audio segments one by one, and return the index and segment content."""
        for segment in self.__segments:
            yield segment

    def length(self) -> int:
        return len(self.__segments)

    def segment_duration(self) -> int:
        return self.__segment_duration


class Response:
    """Response for the streaming ASR protocol, containing the header and payload from the server response, and methods to parse the response content."""

    code: int = 0
    event: int = 0
    is_last_package: bool = False
    payload_sequence: int = 0
    payload_size: int = 0
    payload_msg: dict = None

    def __init__(self, msg: bytes):
        self.header_size = msg[0] & 0x0f
        self.message_type = msg[1] >> 4
        self.message_type_specific_flags = msg[1] & 0x0f
        self.serialization_method = msg[2] >> 4
        self.message_compression = msg[2] & 0x0f
        self.payload = msg[self.header_size*4:]

        # Parse message_type_specific_flags
        if self.message_type_specific_flags & 0x01:
            self.payload_sequence = struct.unpack('>i', self.payload[:4])[0]
            self.payload = self.payload[4:]
        if self.message_type_specific_flags & 0x02:
            self.is_last_package = True
        if self.message_type_specific_flags & 0x04:
            self.event = struct.unpack('>i', self.payload[:4])[0]
            self.payload = self.payload[4:]

        # Parse message_type
        if self.message_type == MessageType.SERVER_FULL_RESPONSE:
            self.payload_size = struct.unpack('>I', self.payload[:4])[0]
            self.payload = self.payload[4:]
        elif self.message_type == MessageType.SERVER_ERROR_RESPONSE:
            self.code = struct.unpack('>i', self.payload[:4])[0]
            self.payload_size = struct.unpack('>I', self.payload[4:8])[0]
            self.payload = self.payload[8:]

        if not self.payload:
            return

        # Uncompress payload if needed
        if self.message_compression == CompressionType.GZIP:
            try:
                self.payload = gzip_decompress(self.payload)
            except Exception as e:
                raise RuntimeError(f"Failed to decompress payload: {e}")

        # Parse payload
        try:
            if self.serialization_method == SerializationType.JSON:
                self.payload_msg = json.loads(self.payload.decode('utf-8'))
        except Exception as e:
            # raise RuntimeError(f"Failed to decompress payload: {e}")
            pass

    def to_dict(self) -> Dict[str, Any]:
        """Convert the response to a dictionary format for easier access."""

        return {
            "code": self.code,
            "event": self.event,
            "is_last_package": self.is_last_package,
            "payload_sequence": self.payload_sequence,
            "payload_size": self.payload_size,
            "payload_msg": self.payload_msg
        }


class Client:
    """Client for Volcengine Streaming ASR SDK.

    NOTE: This client is not thread-safe and should be used within a single asyncio event loop.
    """

    __logger: Logger
    __url: str
    __auth_header: Dict[str, str]
    __session: ClientSession = None
    __conn: ClientWebSocketResponse = None
    __seq: int = 1

    def __init__(self, logger: Logger, url: str, app_key: str, access_key: str,  resource_id: str):
        self.__logger = logger
        self.__url = url
        self.__auth_header = {
            "X-Api-App-Key": app_key,
            "X-Api-Access-Key": access_key,
            "X-Api-Resource-Id": resource_id,
            "X-Api-Request-Id": str(uuid.uuid4())
        }

    async def __aenter__(self) -> 'Client':
        return await self.async_open()

    async def __aexit__(self, exc_type, exc, tb):
        await self.async_close()

    async def async_open(self) -> 'Client':
        """Establish a WebSocket connection to the server."""

        try:
            self.__session = ClientSession()
            self.__conn = await self.__session.ws_connect(self.__url, headers=self.__auth_header)
            self.__seq = 1
            return self
        except Exception as e:
            self.__logger.error(f"Establish connection failed: {e}")
            raise

    async def async_close(self):
        """Close the WebSocket connection."""

        if self.__conn and not self.__conn.closed:
            await self.__conn.close()
        if self.__session and not self.__session.closed:
            await self.__session.close()

    async def async_send_request(self, request: Request):
        """Send a request to the server with the given Request object."""

        try:
            await self.__conn.send_bytes(request.to_bytes(self.__seq))
            self.__seq += 1
        except Exception as e:
            self.__logger.error(f"Fail to send request: {e}")
            raise

    async def async_connect(self, uid: str, language: str,
                            audio_format: str = "wav", audio_codec: str = "raw", audio_rate: int = 16000, audio_bits: int = 16, audio_channels: int = 1,
                            model_name: str = "bigmodel", enable_itn: bool = True, enable_punc: bool = True, enable_ddc: bool = True, show_utterances: bool = True, enable_nonstream: bool = False):
        """Send a request to initialize the ASR session with the given audio parameters and model configuration, and wait for the server response to confirm the connection is established."""

        self.__logger.info("Connect")

        # Send full client request
        await self.async_send_request(
            ConnectRequest(
                uid=uid, language=language,
                audio_format=audio_format, audio_codec=audio_codec, audio_rate=audio_rate, audio_bits=audio_bits, audio_channels=audio_channels,
                model_name=model_name, enable_itn=enable_itn, enable_punc=enable_punc, enable_ddc=enable_ddc, show_utterances=show_utterances, enable_nonstream=enable_nonstream
            )
        )

        # Wait for the server response to confirm the connection is established
        resp = await self.__conn.receive()
        if resp.type != WSMsgType.BINARY:
            self.__logger.error(f"Connect failed, response: {resp}")
            raise RuntimeError(f"Unexpected message type: {resp.type}")
        self.__logger.info(f"Connect success, response: {resp}")

    async def async_disconnect(self):
        """Send a request to indicate the end of the stream and close the connection."""

        self.__logger.info("Disconnect")

        # Send a final request with is_last=True to indicate the end of the stream
        await self.async_send_request(DisconnectRequest())

    async def async_send_segment(self, segment: bytes):
        """Send an audio segment to the server for ASR processing."""

        try:
            await self.async_send_request(SegmentRequest(segment))
        except Exception:
            raise

    async def async_transmit_stream(self, stream: Stream) -> AsyncGenerator:
        """Transmit the audio stream."""

        for segment in stream.read():
            await self.async_send_segment(segment)
            await asyncio.sleep(stream.segment_duration() / 1000)
            yield

    async def async_send_file(self, file_path: str, segment_duration: int = 200, sample_rate: int = 16000) -> AsyncGenerator[Response]:
        """Send an audio file for streaming ASR processing."""

        if not file_path:
            raise ValueError("File path is not existed")

        # Transmit audio stream
        stream = Stream(read_audio_file(
            file_path, sample_rate), segment_duration)
        async for response in self.async_transmit_stream(stream):
            yield response

    async def async_recv(self) -> AsyncGenerator[Response]:
        """Receive responses from the server and yield them as Response objects until the last package is received or an error occurs."""

        try:
            async for msg in self.__conn:
                self.__logger.error(f"{msg}")
                if msg.type == WSMsgType.BINARY:
                    resp = Response(msg.data)

                    if resp.is_last_package:
                        self.__logger.info("Recv completed")
                        break

                    if resp.code != 0:
                        self.__logger.error(
                            f"Connection close with code {resp.code}")
                        raise RuntimeError(
                            f"WebSocket closed unexpectedly: {resp.to_dict()}")

                    yield resp
                elif msg.type == WSMsgType.ERROR:
                    raise RuntimeError(f"WebSocket error: {msg.data}")
                elif msg.type == WSMsgType.CLOSED:
                    raise RuntimeError("WebSocket closed unexpectedly")
        except Exception:
            raise
