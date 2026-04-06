"""Utility functions for Volcengine Voice Assistant SDK
"""

import gzip
import io
import struct
import subprocess
import wave
from typing import Tuple


def gzip_compress(data: bytes) -> bytes:
    """Gzip compress"""
    return gzip.compress(data)


def gzip_decompress(data: bytes) -> bytes:
    """Gzip decompress"""
    return gzip.decompress(data)


def judge_wav(data: bytes) -> bool:
    """Judge a data is wav format"""

    if len(data) < 44:
        return False

    try:
        _ = wave.open(io.BytesIO(data), 'rb')
        return True
    except Exception:
        return False


def gen_wav_content(sample_rate: int, bit_rate: int,
                    channels: int, data: bytes = b"") -> bytes:
    """Generate a wav content from pcm"""
    buff = io.BytesIO()

    # pylint: disable=E1101
    with wave.open(buff, 'wb') as wavf:
        wavf.setframerate(sample_rate)
        wavf.setsampwidth(bit_rate // 8)
        wavf.setnchannels(channels)
        wavf.writeframes(data)

    return buff.getvalue()


def convert_wav_with_path(audio_path: str, sample_rate: int) -> bytes:
    """Covert file to wav format"""
    cmd = [
        "ffmpeg", "-v", "quiet", "-y", "-i", audio_path,
        "-acodec", "pcm_s16le", "-ac", "1", "-ar", str(sample_rate),
        "-f", "wav", "-"
    ]
    result = subprocess.run(
        cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    return result.stdout


def read_wav_info(data: bytes) -> Tuple[int, int, int]:
    """Read wav header

    Return nchannels,sampwidth,framerate
    """
    buff = io.BytesIO(data)
    with wave.open(buff, 'rb') as wavf:
        return [wavf.getnchannels(), wavf.getsampwidth(), wavf.getframerate()]


def read_audio_file(file_path: str, sample_rate: int) -> bytes:
    """Read audio file"""
    with open(file_path, 'rb') as f:
        content = f.read()

    if not judge_wav(content):
        content = convert_wav_with_path(
            file_path, sample_rate)

    return content
