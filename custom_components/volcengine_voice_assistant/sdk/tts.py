"""Text-to-Speech SDK for Volcengine Voice Assistant

This model improve from the official demo code, and is designed to be more user-friendly and easier to integrate into applications.
It provides a simple interface for sending audio data and receiving transcriptions, while handling the underlying protocol details internally.
"""

import io
import json
import logging
import struct
import uuid
from dataclasses import dataclass
from enum import IntEnum
from logging import Logger
from typing import AsyncGenerator, Callable, Dict, List

from aiohttp import ClientSession, ClientWebSocketResponse, WSMsgType

logger = logging.getLogger(__name__)


class MsgType(IntEnum):
    """Message type enumeration"""

    Invalid = 0
    FullClientRequest = 0b1
    AudioOnlyClient = 0b10
    FullServerResponse = 0b1001
    AudioOnlyServer = 0b1011
    FrontEndResultServer = 0b1100
    Error = 0b1111

    # Alias
    ServerACK = AudioOnlyServer

    def __str__(self) -> str:
        return self.name if self.name else f"MsgType({self.value})"


class MsgTypeFlagBits(IntEnum):
    """Message type flag bits"""

    NoSeq = 0  # Non-terminal packet with no sequence
    PositiveSeq = 0b1  # Non-terminal packet with sequence > 0
    LastNoSeq = 0b10  # Last packet with no sequence
    NegativeSeq = 0b11  # Last packet with sequence < 0
    WithEvent = 0b100  # Payload contains event number (int32)


class VersionBits(IntEnum):
    """Version bits"""

    Version1 = 1
    Version2 = 2
    Version3 = 3
    Version4 = 4


class HeaderSizeBits(IntEnum):
    """Header size bits"""

    HeaderSize4 = 1
    HeaderSize8 = 2
    HeaderSize12 = 3
    HeaderSize16 = 4


class SerializationBits(IntEnum):
    """Serialization method bits"""

    Raw = 0
    JSON = 0b1
    Thrift = 0b11
    Custom = 0b1111


class CompressionBits(IntEnum):
    """Compression method bits"""

    None_ = 0
    Gzip = 0b1
    Custom = 0b1111


class EventType(IntEnum):
    """Event type enumeration"""

    None_ = 0  # Default event

    # 1 ~ 49 Upstream Connection events
    StartConnection = 1
    StartTask = 1  # Alias of StartConnection
    FinishConnection = 2
    FinishTask = 2  # Alias of FinishConnection

    # 50 ~ 99 Downstream Connection events
    ConnectionStarted = 50  # Connection established successfully
    TaskStarted = 50  # Alias of ConnectionStarted
    # Connection failed (possibly due to authentication failure)
    ConnectionFailed = 51
    TaskFailed = 51  # Alias of ConnectionFailed
    ConnectionFinished = 52  # Connection ended
    TaskFinished = 52  # Alias of ConnectionFinished

    # 100 ~ 149 Upstream Session events
    StartSession = 100
    CancelSession = 101
    FinishSession = 102

    # 150 ~ 199 Downstream Session events
    SessionStarted = 150
    SessionCanceled = 151
    SessionFinished = 152
    SessionFailed = 153
    UsageResponse = 154  # Usage response
    ChargeData = 154  # Alias of UsageResponse

    # 200 ~ 249 Upstream general events
    TaskRequest = 200
    UpdateConfig = 201

    # 250 ~ 299 Downstream general events
    AudioMuted = 250

    # 300 ~ 349 Upstream TTS events
    SayHello = 300

    # 350 ~ 399 Downstream TTS events
    TTSSentenceStart = 350
    TTSSentenceEnd = 351
    TTSResponse = 352
    TTSEnded = 359
    PodcastRoundStart = 360
    PodcastRoundResponse = 361
    PodcastRoundEnd = 362

    # 450 ~ 499 Downstream ASR events
    ASRInfo = 450
    ASRResponse = 451
    ASREnded = 459

    # 500 ~ 549 Upstream dialogue events
    ChatTTSText = 500  # (Ground-Truth-Alignment) text for speech synthesis

    # 550 ~ 599 Downstream dialogue events
    ChatResponse = 550
    ChatEnded = 559

    # 650 ~ 699 Downstream dialogue events
    # Events for source (original) language subtitle
    SourceSubtitleStart = 650
    SourceSubtitleResponse = 651
    SourceSubtitleEnd = 652
    # Events for target (translation) language subtitle
    TranslationSubtitleStart = 653
    TranslationSubtitleResponse = 654
    TranslationSubtitleEnd = 655

    def __str__(self) -> str:
        return self.name if self.name else f"EventType({self.value})"


@dataclass
class Message:
    """Message object

    Message format:
    0                 1                 2                 3
    | 0 1 2 3 4 5 6 7 | 0 1 2 3 4 5 6 7 | 0 1 2 3 4 5 6 7 | 0 1 2 3 4 5 6 7 |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |    Version      |   Header Size   |     Msg Type    |      Flags      |
    |   (4 bits)      |    (4 bits)     |     (4 bits)    |     (4 bits)    |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    | Serialization   |   Compression   |           Reserved                |
    |   (4 bits)      |    (4 bits)     |           (8 bits)                |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |                                                                       |
    |                   Optional Header Extensions                          |
    |                     (if Header Size > 1)                              |
    |                                                                       |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |                                                                       |
    |                           Payload                                     |
    |                      (variable length)                                |
    |                                                                       |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    """

    version: VersionBits = VersionBits.Version1
    header_size: HeaderSizeBits = HeaderSizeBits.HeaderSize4
    type: MsgType = MsgType.Invalid
    flag: MsgTypeFlagBits = MsgTypeFlagBits.NoSeq
    serialization: SerializationBits = SerializationBits.JSON
    compression: CompressionBits = CompressionBits.None_

    event: EventType = EventType.None_
    session_id: str = ""
    connect_id: str = ""
    sequence: int = 0
    error_code: int = 0

    payload: bytes = b""

    def from_bytes(self, data: bytes) -> "Message":
        """Create message object from bytes"""
        if len(data) < 3:
            raise ValueError(
                f"Data too short: expected at least 3 bytes, got {len(data)}"
            )

        type_and_flag = data[1]
        self.type = MsgType(type_and_flag >> 4)
        self.flag = MsgTypeFlagBits(type_and_flag & 0b00001111)
        self.unmarshal(data)

        return self

    def marshal(self) -> bytes:
        """Serialize message to bytes"""
        buffer = io.BytesIO()

        # Write header
        header = [
            (self.version << 4) | self.header_size,
            (self.type << 4) | self.flag,
            (self.serialization << 4) | self.compression,
        ]

        header_size = 4 * self.header_size
        if padding := header_size - len(header):
            header.extend([0] * padding)

        buffer.write(bytes(header))

        # Write other fields
        writers = self._get_writers()
        for writer in writers:
            writer(buffer)

        return buffer.getvalue()

    def unmarshal(self, data: bytes) -> None:
        """Deserialize message from bytes"""
        buffer = io.BytesIO(data)

        # Read version and header size
        version_and_header_size = buffer.read(1)[0]
        self.version = VersionBits(version_and_header_size >> 4)
        self.header_size = HeaderSizeBits(version_and_header_size & 0b00001111)

        # Skip second byte
        buffer.read(1)

        # Read serialization and compression methods
        serialization_compression = buffer.read(1)[0]
        self.serialization = SerializationBits(serialization_compression >> 4)
        self.compression = CompressionBits(
            serialization_compression & 0b00001111)

        # Skip header padding
        header_size = 4 * self.header_size
        read_size = 3
        if padding_size := header_size - read_size:
            buffer.read(padding_size)

        # Read other fields
        readers = self._get_readers()
        for reader in readers:
            reader(buffer)

        # Check for remaining data
        remaining = buffer.read()
        if remaining:
            raise ValueError(f"Unexpected data after message: {remaining}")

    def _get_writers(self) -> List[Callable[[io.BytesIO], None]]:
        """Get list of writer functions"""
        writers = []

        if self.flag == MsgTypeFlagBits.WithEvent:
            writers.extend([self._write_event, self._write_session_id])

        if self.type in [
            MsgType.FullClientRequest,
            MsgType.FullServerResponse,
            MsgType.FrontEndResultServer,
            MsgType.AudioOnlyClient,
            MsgType.AudioOnlyServer,
        ]:
            if self.flag in [MsgTypeFlagBits.PositiveSeq, MsgTypeFlagBits.NegativeSeq]:
                writers.append(self._write_sequence)
        elif self.type == MsgType.Error:
            writers.append(self._write_error_code)
        else:
            raise ValueError(f"Unsupported message type: {self.type}")

        writers.append(self._write_payload)
        return writers

    def _get_readers(self) -> List[Callable[[io.BytesIO], None]]:
        """Get list of reader functions"""
        readers = []

        if self.type in [
            MsgType.FullClientRequest,
            MsgType.FullServerResponse,
            MsgType.FrontEndResultServer,
            MsgType.AudioOnlyClient,
            MsgType.AudioOnlyServer,
        ]:
            if self.flag in [MsgTypeFlagBits.PositiveSeq, MsgTypeFlagBits.NegativeSeq]:
                readers.append(self._read_sequence)
        elif self.type == MsgType.Error:
            readers.append(self._read_error_code)
        else:
            raise ValueError(f"Unsupported message type: {self.type}")

        if self.flag == MsgTypeFlagBits.WithEvent:
            readers.extend(
                [self._read_event, self._read_session_id, self._read_connect_id]
            )

        readers.append(self._read_payload)
        return readers

    def _write_event(self, buffer: io.BytesIO) -> None:
        """Write event"""
        buffer.write(struct.pack(">i", self.event))

    def _write_session_id(self, buffer: io.BytesIO) -> None:
        """Write session ID"""
        if self.event in [
            EventType.StartConnection,
            EventType.FinishConnection,
            EventType.ConnectionStarted,
            EventType.ConnectionFailed,
        ]:
            return

        session_id_bytes = self.session_id.encode("utf-8")
        size = len(session_id_bytes)
        if size > 0xFFFFFFFF:
            raise ValueError(f"Session ID size ({size}) exceeds max(uint32)")

        buffer.write(struct.pack(">I", size))
        if size > 0:
            buffer.write(session_id_bytes)

    def _write_sequence(self, buffer: io.BytesIO) -> None:
        """Write sequence number"""
        buffer.write(struct.pack(">i", self.sequence))

    def _write_error_code(self, buffer: io.BytesIO) -> None:
        """Write error code"""
        buffer.write(struct.pack(">I", self.error_code))

    def _write_payload(self, buffer: io.BytesIO) -> None:
        """Write payload"""
        size = len(self.payload)
        if size > 0xFFFFFFFF:
            raise ValueError(f"Payload size ({size}) exceeds max(uint32)")

        buffer.write(struct.pack(">I", size))
        buffer.write(self.payload)

    def _read_event(self, buffer: io.BytesIO) -> None:
        """Read event"""
        event_bytes = buffer.read(4)
        if event_bytes:
            self.event = EventType(struct.unpack(">i", event_bytes)[0])

    def _read_session_id(self, buffer: io.BytesIO) -> None:
        """Read session ID"""
        if self.event in [
            EventType.StartConnection,
            EventType.FinishConnection,
            EventType.ConnectionStarted,
            EventType.ConnectionFailed,
            EventType.ConnectionFinished,
        ]:
            return

        size_bytes = buffer.read(4)
        if size_bytes:
            size = struct.unpack(">I", size_bytes)[0]
            if size > 0:
                session_id_bytes = buffer.read(size)
                if len(session_id_bytes) == size:
                    self.session_id = session_id_bytes.decode("utf-8")

    def _read_connect_id(self, buffer: io.BytesIO) -> None:
        """Read connection ID"""
        if self.event in [
            EventType.ConnectionStarted,
            EventType.ConnectionFailed,
            EventType.ConnectionFinished,
        ]:
            size_bytes = buffer.read(4)
            if size_bytes:
                size = struct.unpack(">I", size_bytes)[0]
                if size > 0:
                    self.connect_id = buffer.read(size).decode("utf-8")

    def _read_sequence(self, buffer: io.BytesIO) -> None:
        """Read sequence number"""
        sequence_bytes = buffer.read(4)
        if sequence_bytes:
            self.sequence = struct.unpack(">i", sequence_bytes)[0]

    def _read_error_code(self, buffer: io.BytesIO) -> None:
        """Read error code"""
        error_code_bytes = buffer.read(4)
        if error_code_bytes:
            self.error_code = struct.unpack(">I", error_code_bytes)[0]

    def _read_payload(self, buffer: io.BytesIO) -> None:
        """Read payload"""
        size_bytes = buffer.read(4)
        if size_bytes:
            size = struct.unpack(">I", size_bytes)[0]
            if size > 0:
                self.payload = buffer.read(size)

    def __str__(self) -> str:
        """String representation"""
        if self.type in [MsgType.AudioOnlyServer, MsgType.AudioOnlyClient]:
            if self.flag in [MsgTypeFlagBits.PositiveSeq, MsgTypeFlagBits.NegativeSeq]:
                return f"MsgType: {self.type}, EventType:{self.event}, Sequence: {self.sequence}, PayloadSize: {len(self.payload)}"
            return f"MsgType: {self.type}, EventType:{self.event}, PayloadSize: {len(self.payload)}"
        elif self.type == MsgType.Error:
            return f"MsgType: {self.type}, EventType:{self.event}, ErrorCode: {self.error_code}, Payload: {self.payload.decode('utf-8', 'ignore')}"
        else:
            if self.flag in [MsgTypeFlagBits.PositiveSeq, MsgTypeFlagBits.NegativeSeq]:
                return f"MsgType: {self.type}, EventType:{self.event}, Sequence: {self.sequence}, Payload: {self.payload.decode('utf-8', 'ignore')}"
            return f"MsgType: {self.type}, EventType:{self.event}, Payload: {self.payload.decode('utf-8', 'ignore')}"


class ConnectRequest(Message):
    def __init__(self):
        self.type = MsgType.FullClientRequest
        self.flag = MsgTypeFlagBits.WithEvent
        self.event = EventType.StartConnection
        self.payload = b"{}"


class DisconnectRequest(Message):
    def __init__(self):
        self.type = MsgType.FullClientRequest
        self.flag = MsgTypeFlagBits.WithEvent
        self.event = EventType.FinishConnection
        self.payload = b"{}"


class StartSessionRequest(Message):
    def __init__(self, session_id: str, voice_type: str, encoding: str, sample_rate: int, enable_timestamp: bool, disable_markdown_filter: bool):
        self.type = MsgType.FullClientRequest
        self.flag = MsgTypeFlagBits.WithEvent
        self.event = EventType.StartSession
        self.session_id = session_id
        self.payload = json.dumps(
            {
                "user": {
                    "uid": str(uuid.uuid4()),
                },
                "event": EventType.StartSession,
                "namespace": "BidirectionalTTS",
                "req_params": {
                    "speaker": voice_type,
                    "audio_params": {
                        "format": encoding,
                        "sample_rate": sample_rate,
                        "enable_timestamp": enable_timestamp,
                    },
                    "additions": json.dumps(
                        {
                            "disable_markdown_filter": disable_markdown_filter,
                        }
                    ),
                },
            }
        ).encode()


class FinishSessionRequest(Message):
    def __init__(self, session_id: str):
        self.type = MsgType.FullClientRequest
        self.flag = MsgTypeFlagBits.WithEvent
        self.event = EventType.FinishSession
        self.session_id = session_id
        self.payload = b"{}"


class CancelSessionRequest(Message):
    def __init__(self, session_id: str):
        self.type = MsgType.FullClientRequest
        self.flag = MsgTypeFlagBits.WithEvent
        self.event = EventType.CancelSession
        self.session_id = session_id
        self.payload = b"{}"


class TaskRequest(Message):
    def __init__(self, session_id: str, text: str, voice_type: str, encoding: str, sample_rate: int, enable_timestamp: bool, disable_markdown_filter: bool):
        self.type = MsgType.FullClientRequest
        self.flag = MsgTypeFlagBits.WithEvent
        self.event = EventType.TaskRequest
        self.session_id = session_id
        self.payload = json.dumps(
            {
                "user": {
                    "uid": str(uuid.uuid4()),
                },
                "event": EventType.TaskRequest,
                "namespace": "BidirectionalTTS",
                "req_params": {
                    "speaker": voice_type,
                    "audio_params": {
                        "format": encoding,
                        "sample_rate": sample_rate,
                        "enable_timestamp": enable_timestamp,
                    },
                    "additions": json.dumps(
                        {
                            "disable_markdown_filter": disable_markdown_filter,
                        }
                    ),
                    "text": text,
                },
            }
        ).encode()


class Response(Message):
    def __init__(self, data: bytes):
        self.from_bytes(data)


class Client:
    """Client for Volcengine Streaming TTS SDK.

    NOTE: This client is not thread-safe and should be used within a single asyncio event loop.
    """

    __logger: logging.Logger
    __url: str
    __auth_header: Dict[str, str]
    __session: ClientSession = None
    __conn: ClientWebSocketResponse = None

    __session_id: str
    __voice_type: str
    __encoding: str
    __sample_rate: int
    __enable_timestamp: bool
    __disable_markdown_filter: bool

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

    async def async_send_request(self, message: Message):
        await self.__conn.send_bytes(message.marshal())

    async def async_recv_response(self) -> 'Response':
        msg = await self.__conn.receive()
        if msg.type != WSMsgType.BINARY:
            raise ValueError(f"Unexpected message type: {msg.type}")
        return Response(msg.data)

    async def async_wait_for_event(self, msg_type: MsgType, event_type: EventType,) -> Message:
        """Wait for specific event"""

        resp: Response = await self.async_recv_response()
        if resp.type != msg_type or resp.event != event_type:
            raise ValueError(f"Unexpected message: {resp}")

        return resp

    async def async_connect(self):
        self.__logger.info("Connect")

        await self.async_send_request(ConnectRequest())

        resp: Response = await self.async_wait_for_event(MsgType.FullServerResponse, EventType.ConnectionStarted)
        self.__logger.info(f"Connect success, response: {resp}")

    async def async_disconnect(self):
        self.__logger.info("Disconnect")

        await self.async_send_request(DisconnectRequest())

        resp: Response = await self.async_wait_for_event(MsgType.FullServerResponse, EventType.ConnectionFinished)
        self.__logger.info(f"Disonnect success, response: {resp}")

    async def async_start_session(self, session_id: str, voice_type: str, encoding: str = "mp3", sample_rate: int = 24000, enable_timestamp: bool = True, disable_markdown_filter: bool = False):
        """Start session"""

        self.__session_id = session_id
        self.__voice_type = voice_type
        self.__encoding = encoding
        self.__sample_rate = sample_rate
        self.__enable_timestamp = enable_timestamp
        self.__disable_markdown_filter = disable_markdown_filter

        self.__logger.info("Start disconnect")

        await self.async_send_request(StartSessionRequest(session_id, voice_type, encoding, sample_rate, enable_timestamp, disable_markdown_filter))

        resp: Response = await self.async_wait_for_event(MsgType.FullServerResponse, EventType.SessionStarted)
        self.__logger.info(f"Start session success, response: {resp}")

    async def async_finish_session(self):
        """Finish session"""

        self.__logger.info("Finish disconnect")

        await self.async_send_request(FinishSessionRequest(self.__session_id))

    async def async_cancel_session(self):
        """Finish session"""

        self.__logger.info("Cancel disconnect")

        await self.async_send_request(CancelSessionRequest(self.__session_id))

    async def async_send_task(self, text: bytes):
        """Send task request"""

        await self.async_send_request(TaskRequest(self.__session_id, text, self.__voice_type, self.__encoding, self.__sample_rate, self.__enable_timestamp, self.__disable_markdown_filter))

    async def async_recv(self) -> AsyncGenerator[Response]:
        """Receive responses from the server and yield them as Response objects until the session finished or an error occurs."""

        async for msg in self.__conn:
            if msg.type != WSMsgType.BINARY:
                raise ValueError(f"Recv unexpectedly MsgType: {msg.type})=")

            resp = Response(msg.data)

            if resp.type == MsgType.FullServerResponse and resp.event == EventType.SessionFinished:
                break

            yield resp
