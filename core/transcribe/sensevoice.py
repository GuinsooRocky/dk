"""本地 SenseVoice 识别（sherpa-onnx）。复用 MK 已下好的模型 + MK 趟过的参数。

K值来自 MK client/scripts/measure-sensevoice.py：use_itn=True, num_threads=4。
关键坑（MK 生产踩过）：language 写死 'zh'，不开 auto —— auto LID 会把中英混说误判成日文假名。
模型路径默认指 MK 的 ~/.mk/models/...；分发到没 MK 的机器要改 SENSEVOICE_DIR 或后续加自动下载。
"""
import os
import threading
from pathlib import Path

_DEFAULT_DIR = Path.home() / ".mk" / "models" / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
_DIR = Path(os.getenv("SENSEVOICE_DIR", str(_DEFAULT_DIR))).expanduser()

_rec = None
_lock = threading.Lock()


def _recognizer():
    """懒加载 + 单例（模型 228MB，只建一次）。"""
    global _rec
    if _rec is not None:
        return _rec
    with _lock:
        if _rec is None:
            import sherpa_onnx
            model = _DIR / "model.int8.onnx"
            tokens = _DIR / "tokens.txt"
            if not model.exists() or not tokens.exists():
                raise FileNotFoundError(
                    f"SenseVoice 模型缺失：{_DIR}。设 SENSEVOICE_DIR 指向模型目录，"
                    f"或放入 MK 模型(model.int8.onnx + tokens.txt)。"
                )
            _rec = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=str(model), tokens=str(tokens),
                language="zh", use_itn=True, num_threads=4,
            )
    return _rec


def recognize(samples, sample_rate) -> str:
    rec = _recognizer()
    stream = rec.create_stream()
    stream.accept_waveform(sample_rate, samples)
    rec.decode_stream(stream)
    return (stream.result.text or "").strip()
