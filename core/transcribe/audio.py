"""音频解码：任意格式 → 16k 单声道 wav，再读成 float32 给 sherpa。"""
import os
import wave
import subprocess
from pathlib import Path

import numpy as np

FFMPEG = os.getenv("FFMPEG_CMD", "ffmpeg")


def to_wav16k_mono(src_path, dst_path) -> None:
    """用 ffmpeg 转 16kHz 单声道 wav（SenseVoice 要求）。失败抛 CalledProcessError。"""
    subprocess.run(
        [FFMPEG, "-y", "-i", str(src_path), "-ar", "16000", "-ac", "1", "-f", "wav", str(dst_path)],
        check=True, capture_output=True,
    )


def read_wav_f32(path):
    """读 16-bit PCM wav → (sample_rate, float32 ndarray in [-1,1])。"""
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        raw = w.readframes(w.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return sr, samples
