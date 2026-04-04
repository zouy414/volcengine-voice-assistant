"""Utility functions for Volcengine Voice Assistant SDK
"""

import gzip
import io
import os
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
    # wav header = 44 bytes
    byte_rate = sample_rate * channels * int(bit_rate / 8)
    block_align = channels * int(bit_rate / 8)
    data_size = len(data)
    data_buff = bytearray()
    data_buff.extend(data)

    buf = io.BytesIO()
    buf.write(b'RIFF')
    buf.write(struct.pack('<I', 36 + data_size))
    buf.write(b'WAVEfmt ')
    buf.write(struct.pack('<I', 16))  # Subchunk1Size (16 for PCM)
    buf.write(struct.pack('<H', 1))   # AudioFormat PCM = 1
    buf.write(struct.pack('<H', channels))
    buf.write(struct.pack('<I', sample_rate))
    buf.write(struct.pack('<I', byte_rate))
    buf.write(struct.pack('<H', block_align))
    buf.write(struct.pack('<H', bit_rate))  # bits per sample
    buf.write(b'data')
    buf.write(struct.pack('<I', data_size))
    buf.write(data_buff)

    return buf.getvalue()


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
