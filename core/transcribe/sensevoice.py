"""本地 SenseVoice 识别（sherpa-onnx）。复用 MK 已下好的模型 + MK 趟过的参数。

K值来自 MK client/scripts/measure-sensevoice.py：use_itn=True, num_threads=4。
关键坑（MK 生产踩过）：language 写死 'zh'，不开 auto —— auto LID 会把中英混说误判成日文假名。
模型查找「有就用、缺才下」：SENSEVOICE_DIR → MK 目录 → DK 目录，全缺才从 HuggingFace
懒下载一次到 DK 目录（不写 MK 地盘，DK/MK 解耦）；本机有 MK 模型则永不触发下载。
"""
import os
import threading
from pathlib import Path

_MODEL_NAME = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
_MK_DIR = Path.home() / ".mk" / "models" / _MODEL_NAME   # MK 地盘，只读复用，绝不写
_DK_DIR = Path.home() / ".dk" / "models" / _MODEL_NAME   # DK 自己的下载落点
_HF_REPO = "csukuangfj/" + _MODEL_NAME
_MODEL_FILES = ("model.int8.onnx", "tokens.txt")

_rec = None
_lock = threading.Lock()


def _has_model(d: Path) -> bool:
    return all((d / f).exists() for f in _MODEL_FILES)


def _resolve_dir():
    """按顺序找已存在的模型目录，命中即用、不下载。全缺返回 None。"""
    candidates = []
    env = os.getenv("SENSEVOICE_DIR")
    if env:
        candidates.append(Path(env).expanduser())
    candidates += [_MK_DIR, _DK_DIR]
    for d in candidates:
        if _has_model(d):
            return d
    return None


def _ensure_model():
    """有就用、缺才下：返回一个含模型的目录。三处都缺才从 HuggingFace 下到 DK 目录。

    用 stdlib urllib，不引重依赖；失败给清晰报错（保留手动设 SENSEVOICE_DIR 的兜底文案）。
    """
    found = _resolve_dir()
    if found is not None:
        return found

    import urllib.request   # 函数内懒导入，保持模块顶层轻量

    _DK_DIR.mkdir(parents=True, exist_ok=True)
    for fname in _MODEL_FILES:
        dest = _DK_DIR / fname
        if dest.exists():
            continue
        url = f"https://huggingface.co/{_HF_REPO}/resolve/main/{fname}"
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            urllib.request.urlretrieve(url, tmp)   # 模型 ~228MB，仅首用触发一次
            tmp.replace(dest)
        except Exception as e:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise FileNotFoundError(
                f"SenseVoice 模型自动下载失败（{url}）：{e}。"
                f"可手动把 {list(_MODEL_FILES)} 放到 {_DK_DIR}，"
                f"或设 SENSEVOICE_DIR 指向已有模型目录。"
            ) from e
    return _DK_DIR


def _recognizer():
    """懒加载 + 单例（模型 228MB，只建一次）。"""
    global _rec
    if _rec is not None:
        return _rec
    with _lock:
        if _rec is None:
            import sherpa_onnx
            model_dir = _ensure_model()   # 有就用、缺才下；返回的目录保证有模型
            model = model_dir / "model.int8.onnx"
            tokens = model_dir / "tokens.txt"
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
