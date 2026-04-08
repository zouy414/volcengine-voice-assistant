"""Text-to-Speech SDK for Volcengine Voice Assistant

This model improve from the official demo code, and is designed to be more user-friendly and easier to integrate into applications.
It provides a simple interface for sending audio data and receiving transcriptions, while handling the underlying protocol details internally.
"""

import io
import json
import struct
import uuid
from dataclasses import dataclass
from enum import IntEnum
from typing import AsyncGenerator, Callable, Dict, List, Tuple

from aiohttp import ClientSession, ClientWebSocketResponse, WSMsgType


class MsgType(IntEnum):
    """Message type enumeration"""

    INVALID = 0
    FULL_CLIENT_REQUEST = 0b1
    AUDIO_ONLY_CLIENT = 0b10
    FULL_SERVER_RESPONSE = 0b1001
    AUDIO_ONLY_SERVER = 0b1011
    FRONT_END_RESULT_SERVER = 0b1100
    ERROR = 0b1111

    # Alias
    SERVER_ACK = AUDIO_ONLY_SERVER

    def __str__(self) -> str:
        return self.name if self.name else f"MsgType({self.value})"


class MsgTypeFlagBits(IntEnum):
    """Message type flag bits"""

    NO_SEQ = 0  # Non-terminal packet with no sequence
    POSITIVE_SEQ = 0b1  # Non-terminal packet with sequence > 0
    LAST_NO_SEQ = 0b10  # Last packet with no sequence
    NEGATIVE_SEQ = 0b11  # Last packet with sequence < 0
    WITH_EVENT = 0b100  # Payload contains event number (int32)


class VersionBits(IntEnum):
    """Version bits"""

    VERSION_1 = 1
    VERSION_2 = 2
    VERSION_3 = 3
    VERSION_4 = 4


class HeaderSizeBits(IntEnum):
    """Header size bits"""

    HEADER_SIZE_4 = 1
    HEADER_SIZE_8 = 2
    HEADER_SIZE_12 = 3
    HEADER_SIZE_16 = 4


class SerializationBits(IntEnum):
    """Serialization method bits"""

    RAW = 0
    JSON = 0b1
    THRIFT = 0b11
    CUSTOM = 0b1111


class CompressionBits(IntEnum):
    """Compression method bits"""

    NONE = 0
    GZIP = 0b1
    CUSTOM = 0b1111


class EventType(IntEnum):
    """Event type enumeration"""

    NONE = 0  # Default event

    # 1 ~ 49 Upstream Connection events
    START_CONNECTION = 1
    START_TASK = 1  # Alias of START_CONNECTION
    FINISH_CONNECTION = 2
    FINISH_TASK = 2  # Alias of FINISH_CONNECTION

    # 50 ~ 99 Downstream Connection events
    CONNECTION_START = 50  # Connection established successfully
    TASK_START = 50  # Alias of CONNECTION_START
    # Connection failed (possibly due to authentication failure)
    CONNECTION_FAILED = 51
    TASK_FAILED = 51  # Alias of CONNECTION_FAILED
    CONNECTION_FINISH = 52  # Connection ended
    TASK_FINISH = 52  # Alias of CONNECTION_FINISH

    # 100 ~ 149 Upstream Session events
    START_SESSION = 100
    CANCEL_SESSION = 101
    FINISH_SESSION = 102

    # 150 ~ 199 Downstream Session events
    SESSION_START = 150
    SESSION_CANCELED = 151
    SESSION_FINISHED = 152
    SESSION_FAILED = 153
    USAGE_RESPONSE = 154  # Usage response
    CHARGE_DATA = 154  # Alias of USAGE_RESPONSE

    # 200 ~ 249 Upstream general events
    TASK_REQUEST = 200
    UPDATE_CONFIG = 201

    # 250 ~ 299 Downstream general events
    AUDIO_MUTED = 250

    # 300 ~ 349 Upstream TTS events
    SAY_HELLO = 300

    # 350 ~ 399 Downstream TTS events
    TTS_SENTENCE_START = 350
    TTS_SENTENCE_END = 351
    TTS_RESPONSE = 352
    TTS_ENDED = 359
    POD_CAST_ROUND_START = 360
    POD_CAST_ROUND_RESPONSE = 361
    POD_CAST_ROUND_END = 362

    # 450 ~ 499 Downstream ASR events
    ASR_INFO = 450
    ASR_RESPONSE = 451
    ASR_ENDED = 459

    # 500 ~ 549 Upstream dialogue events
    CHAT_TTS_TEXT = 500  # (Ground-Truth-Alignment) text for speech synthesis

    # 550 ~ 599 Downstream dialogue events
    CHAT_RESPONSE = 550
    CHAT_ENDED = 559

    # 650 ~ 699 Downstream dialogue events
    # Events for source (original) language subtitle
    SOURCE_SUBTITLE_START = 650
    SOURCE_SUBTITLE_RESPONSE = 651
    SOURCE_SUBTITLE_END = 652
    # Events for target (translation) language subtitle
    TRANSLATION_SUBTITLE_START = 653
    TRANSLATION_SUBTITLE_RESPONSE = 654
    TRANSLATION_SUBTITLE_END = 655

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

    version: VersionBits = VersionBits.VERSION_1
    header_size: HeaderSizeBits = HeaderSizeBits.HEADER_SIZE_4
    type: MsgType = MsgType.INVALID
    flag: MsgTypeFlagBits = MsgTypeFlagBits.NO_SEQ
    serialization: SerializationBits = SerializationBits.JSON
    compression: CompressionBits = CompressionBits.NONE

    event: EventType = EventType.NONE
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

        if self.flag == MsgTypeFlagBits.WITH_EVENT:
            writers.extend([self._write_event, self._write_session_id])

        if self.type in [
            MsgType.FULL_CLIENT_REQUEST,
            MsgType.FULL_SERVER_RESPONSE,
            MsgType.FRONT_END_RESULT_SERVER,
            MsgType.AUDIO_ONLY_CLIENT,
            MsgType.AUDIO_ONLY_SERVER,
        ]:
            if self.flag in [MsgTypeFlagBits.POSITIVE_SEQ,
                             MsgTypeFlagBits.NEGATIVE_SEQ]:
                writers.append(self._write_sequence)
        elif self.type == MsgType.ERROR:
            writers.append(self._write_error_code)
        else:
            raise ValueError(f"Unsupported message type: {self.type}")

        writers.append(self._write_payload)
        return writers

    def _get_readers(self) -> List[Callable[[io.BytesIO], None]]:
        """Get list of reader functions"""
        readers = []

        if self.type in [
            MsgType.FULL_CLIENT_REQUEST,
            MsgType.FULL_SERVER_RESPONSE,
            MsgType.FRONT_END_RESULT_SERVER,
            MsgType.AUDIO_ONLY_CLIENT,
            MsgType.AUDIO_ONLY_SERVER,
        ]:
            if self.flag in [MsgTypeFlagBits.POSITIVE_SEQ,
                             MsgTypeFlagBits.NEGATIVE_SEQ]:
                readers.append(self._read_sequence)
        elif self.type == MsgType.ERROR:
            readers.append(self._read_error_code)
        else:
            raise ValueError(f"Unsupported message type: {self.type}")

        if self.flag == MsgTypeFlagBits.WITH_EVENT:
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
            EventType.START_CONNECTION,
            EventType.FINISH_CONNECTION,
            EventType.CONNECTION_START,
            EventType.CONNECTION_FAILED,
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
            EventType.START_CONNECTION,
            EventType.FINISH_CONNECTION,
            EventType.CONNECTION_START,
            EventType.CONNECTION_FAILED,
            EventType.CONNECTION_FINISH,
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
            EventType.CONNECTION_START,
            EventType.CONNECTION_FAILED,
            EventType.CONNECTION_FINISH,
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
        if self.type in [MsgType.AUDIO_ONLY_SERVER, MsgType.AUDIO_ONLY_CLIENT]:
            if self.flag in [MsgTypeFlagBits.POSITIVE_SEQ,
                             MsgTypeFlagBits.NEGATIVE_SEQ]:
                return f"MsgType: {self.type}, EventType:{self.event}, Sequence: {self.sequence}, PayloadSize: {len(self.payload)}"
            return f"MsgType: {self.type}, EventType:{self.event}, PayloadSize: {len(self.payload)}"

        if self.type == MsgType.ERROR:
            return f"MsgType: {self.type}, EventType:{self.event}, ErrorCode: {self.error_code}, Payload: {self.payload.decode('utf-8', 'ignore')}"

        if self.flag in [MsgTypeFlagBits.POSITIVE_SEQ,
                         MsgTypeFlagBits.NEGATIVE_SEQ]:
            return f"MsgType: {self.type}, EventType:{self.event}, Sequence: {self.sequence}, Payload: {self.payload.decode('utf-8', 'ignore')}"

        return f"MsgType: {self.type}, EventType:{self.event}, Payload: {self.payload.decode('utf-8', 'ignore')}"


class ConnectRequest(Message):
    """Connect request"""

    def __init__(self):
        super().__init__(
            type=MsgType.FULL_CLIENT_REQUEST,
            flag=MsgTypeFlagBits.WITH_EVENT,
            event=EventType.START_CONNECTION,
            payload=b"{}"
        )


class DisconnectRequest(Message):
    """Disconnect request"""

    def __init__(self):
        super().__init__(
            type=MsgType.FULL_CLIENT_REQUEST,
            flag=MsgTypeFlagBits.WITH_EVENT,
            event=EventType.FINISH_CONNECTION,
            payload=b"{}"
        )


class StartSessionRequest(Message):
    """StartSession request"""

    def __init__(self, uid: str, session_id: str, voice_type: str, encoding: str,
                 sample_rate: int, enable_timestamp: bool, disable_markdown_filter: bool):
        super().__init__(
            type=MsgType.FULL_CLIENT_REQUEST,
            flag=MsgTypeFlagBits.WITH_EVENT,
            event=EventType.START_SESSION,
            session_id=session_id,
            payload=json.dumps(
                {
                    "user": {
                        "uid": uid,
                    },
                    "event": EventType.START_SESSION,
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
        )


class FinishSessionRequest(Message):
    """FinishSession request"""

    def __init__(self, session_id: str):
        super().__init__(
            type=MsgType.FULL_CLIENT_REQUEST,
            flag=MsgTypeFlagBits.WITH_EVENT,
            event=EventType.FINISH_SESSION,
            session_id=session_id,
            payload=b"{}"
        )


class CancelSessionRequest(Message):
    """CancelSession request"""

    def __init__(self, session_id: str):
        super().__init__(
            type=MsgType.FULL_CLIENT_REQUEST,
            flag=MsgTypeFlagBits.WITH_EVENT,
            event=EventType.CANCEL_SESSION,
            session_id=session_id,
            payload=b"{}"
        )


class TaskRequest(Message):
    """Task request"""

    def __init__(self, uid: str, session_id: str, text: str, voice_type: str, encoding: str,
                 sample_rate: int, enable_timestamp: bool, disable_markdown_filter: bool):
        super().__init__(
            type=MsgType.FULL_CLIENT_REQUEST,
            flag=MsgTypeFlagBits.WITH_EVENT,
            event=EventType.TASK_REQUEST,
            session_id=session_id,
            payload=json.dumps(
                {
                    "user": {
                        "uid": uid,
                    },
                    "event": EventType.TASK_REQUEST,
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
        )


class Response(Message):
    """Response"""

    def __init__(self, data: bytes):
        super().__init__()
        self.from_bytes(data)


class Client:
    """Client for Volcengine Streaming TTS SDK.

    NOTE: This client is not thread-safe and should be used within a single asyncio event loop.
    """

    __url: str
    __auth_header: Dict[str, str]
    __session: ClientSession = None
    __conn: ClientWebSocketResponse = None

    __uid: str
    __session_id: str
    __voice_type: str
    __encoding: str
    __sample_rate: int
    __enable_timestamp: bool
    __disable_markdown_filter: bool

    def __init__(self, url: str, app_key: str,
                 access_key: str, resource_id: str):
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
        self.__session = ClientSession()
        self.__conn = await self.__session.ws_connect(self.__url, headers=self.__auth_header)
        return self

    async def async_close(self):
        """Close the WebSocket connection."""
        if self.__conn and not self.__conn.closed:
            await self.__conn.close()
        if self.__session and not self.__session.closed:
            await self.__session.close()

    async def async_send_request(self, message: Message):
        """Send request"""
        await self.__conn.send_bytes(message.marshal())

    async def async_recv_response(self, timeout: float = 30) -> Response:
        """Recn response"""
        msg = await self.__conn.receive(timeout)
        if msg.type != WSMsgType.BINARY:
            raise ValueError(f"Unexpected message type: {msg}")
        return Response(msg.data)

    async def async_wait_for_event(
            self, msg_type: MsgType, event_type: EventType) -> Message:
        """Wait for specific event"""
        resp: Response = await self.async_recv_response()
        if resp.type != msg_type or resp.event != event_type:
            raise ValueError(f"Unexpected response: {resp}")

        return resp

    async def async_connect(self) -> Response:
        """Send connect request to server"""
        await self.async_send_request(ConnectRequest())
        return await self.async_wait_for_event(MsgType.FULL_SERVER_RESPONSE, EventType.CONNECTION_START)

    async def async_disconnect(self) -> Response:
        """Send disconnect request to server"""
        await self.async_send_request(DisconnectRequest())
        return await self.async_wait_for_event(MsgType.FULL_SERVER_RESPONSE, EventType.CONNECTION_FINISH)

    async def async_start_session(self, uid: str, voice_type: str, encoding: str = "mp3",
                                  sample_rate: int = 24000, enable_timestamp: bool = True, disable_markdown_filter: bool = False) -> Tuple[str, Response]:
        """Start session"""
        self.__uid = uid
        self.__session_id = str(uuid.uuid4())
        self.__voice_type = voice_type
        self.__encoding = encoding
        self.__sample_rate = sample_rate
        self.__enable_timestamp = enable_timestamp
        self.__disable_markdown_filter = disable_markdown_filter

        await self.async_send_request(StartSessionRequest(uid, self.__session_id, voice_type, encoding, sample_rate, enable_timestamp, disable_markdown_filter))
        return (self.__session_id, await self.async_wait_for_event(MsgType.FULL_SERVER_RESPONSE, EventType.SESSION_START))

    async def async_finish_session(self):
        """Finish session"""
        await self.async_send_request(FinishSessionRequest(self.__session_id))

    async def async_cancel_session(self):
        """Finish session"""
        await self.async_send_request(CancelSessionRequest(self.__session_id))

    async def async_send_task(self, text: bytes):
        """Send task request"""
        await self.async_send_request(TaskRequest(self.__uid, self.__session_id, text, self.__voice_type, self.__encoding, self.__sample_rate, self.__enable_timestamp, self.__disable_markdown_filter))

    async def async_recv(
            self, timeout: float = 30) -> AsyncGenerator[Response]:
        """Receive responses from the server and yield them as Response objects until the session finished or an error occurs."""
        while True:
            msg = await self.__conn.receive(timeout=timeout)
            if msg.type != WSMsgType.BINARY:
                raise ValueError(
                    f"Recv unexpectedly MsgType: {msg.type})=")

            resp = Response(msg.data)

            if resp.type == MsgType.FULL_SERVER_RESPONSE and resp.event == EventType.SESSION_FINISHED:
                break

            yield resp
