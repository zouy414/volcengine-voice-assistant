"""Utility functions for Volcengine Voice Assistant SDK
"""

import gzip
import io
import struct
import subprocess
import wave
from typing import Tuple


def gzip_compress(data: bytes) -> bytes:
    return gzip.compress(data)


def gzip_decompress(data: bytes) -> bytes:
    return gzip.decompress(data)


def judge_wav(data: bytes) -> bool:
    if len(data) < 44:
        return False

    try:
        _ = wave.open(io.BytesIO(data), 'rb')
        return True
    except Exception:
        return False


def gen_wav_segment(sample_rate: int, bit_rate: int, channels: int, data: bytes = b"") -> bytes:
    buff = io.BytesIO()

    with wave.open(buff, 'wb') as wavf:
        wavf.setframerate(sample_rate)
        wavf.setsampwidth(bit_rate // 8)
        wavf.setnchannels(channels)
        wavf.writeframes(data)

    return buff.getvalue()


def convert_wav_with_path(audio_path: str, sample_rate: int) -> bytes:
    try:
        cmd = [
            "ffmpeg", "-v", "quiet", "-y", "-i", audio_path,
            "-acodec", "pcm_s16le", "-ac", "1", "-ar", str(sample_rate),
            "-f", "wav", "-"
        ]
        result = subprocess.run(
            cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        return result.stdout
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Audio conversion failed: {e.stderr.decode()}")


def read_wav_info(data: bytes) -> Tuple[int, int, int, int, bytes]:
    if len(data) < 44:
        raise ValueError("Invalid WAV file: too short")

    # Parse WAV header
    chunk_id = data[:4]
    if chunk_id != b'RIFF':
        raise ValueError("Invalid WAV file: not RIFF format")
    format_ = data[8:12]
    if format_ != b'WAVE':
        raise ValueError("Invalid WAV file: not WAVE format")

    # Parse fmt subchunk
    audio_format = struct.unpack('<H', data[20:22])[0]
    num_channels = struct.unpack('<H', data[22:24])[0]
    sample_rate = struct.unpack('<I', data[24:28])[0]
    bits_per_sample = struct.unpack('<H', data[34:36])[0]

    # Parse data subchunk
    pos = 36
    while pos < len(data) - 8:
        subchunk_id = data[pos:pos+4]
        subchunk_size = struct.unpack('<I', data[pos+4:pos+8])[0]
        if subchunk_id == b'data':
            wave_data = data[pos+8:pos+8+subchunk_size]
            return (
                num_channels,
                bits_per_sample // 8,
                sample_rate,
                subchunk_size // (num_channels * (bits_per_sample // 8)),
                wave_data
            )
        pos += 8 + subchunk_size
    raise ValueError("Invalid WAV file: no data subchunk found")


def read_audio_file(file_path: str, sample_rate: int) -> bytes:
    with open(file_path, 'rb') as f:
        content = f.read()

    if not judge_wav(content):
        content = convert_wav_with_path(
            file_path, sample_rate)

    return content
