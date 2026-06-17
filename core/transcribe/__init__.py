"""语音转写 —— 任意音频文件 → 文字。

默认引擎：本地 SenseVoice（复用 MK 已下好的模型，离线免费）。
链路：ffmpeg 解码成 16k 单声道 wav → sherpa-onnx SenseVoice 识别。
未来要加 Groq/腾讯等云端引擎，在这里按 ASR_ENGINE 分流即可（目前只本地）。
"""
import tempfile
from pathlib import Path

from . import audio, sensevoice


def transcribe(src_audio_path) -> str:
    """音频文件（ogg/mp3/m4a/wav…）→ 文字。同步阻塞（ffmpeg+解码），调用方需丢线程池。"""
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "a.wav"
        audio.to_wav16k_mono(src_audio_path, wav)
        sr, samples = audio.read_wav_f32(wav)
    return sensevoice.recognize(samples, sr)
