"""
Audio preprocessing utilities.

Responsibilities:
  - Load audio from raw bytes (browser upload) or file path
  - Convert to mono float32
  - Resample to 16 kHz
  - Trim to max duration
  - Peak-normalise
"""
from __future__ import annotations

import io
import numpy as np
import soundfile as sf
import librosa
from pathlib import Path
from typing import Tuple
import logging

logger = logging.getLogger(__name__)

TARGET_SR = 16000


def load_audio(data: bytes | str | Path) -> Tuple[np.ndarray, int]:
    """
    Load audio from bytes (file upload) or a file path.

    Returns
    -------
    audio : np.ndarray
        Float32 mono waveform.
    sr : int
        Original sample rate.
    """
    if isinstance(data, (str, Path)):
        audio, sr = sf.read(str(data), dtype="float32", always_2d=False)
    else:
        audio, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=False)

    if audio.ndim > 1:
        audio = audio.mean(axis=1)  # stereo → mono

    return audio, sr


def resample(audio: np.ndarray, orig_sr: int, target_sr: int = TARGET_SR) -> np.ndarray:
    """Resample audio to ``target_sr``; no-op if already at target rate."""
    if orig_sr == target_sr:
        return audio
    return librosa.resample(audio, orig_sr=orig_sr, target_sr=target_sr)


def normalize(audio: np.ndarray) -> np.ndarray:
    """Peak-normalise audio to the range [-1, 1]."""
    peak = np.abs(audio).max()
    return audio / peak if peak > 0 else audio


def preprocess_bytes(
    data: bytes,
    target_sr: int = TARGET_SR,
    max_duration_s: float = 60.0,
) -> np.ndarray:
    """
    Complete preprocessing pipeline for raw uploaded audio bytes.

    Steps:
      1. Load audio (soundfile; pydub fallback for webm/mp4)
      2. Mix to mono
      3. Resample to ``target_sr``
      4. Trim to ``max_duration_s``
      5. Peak-normalise

    Returns
    -------
    np.ndarray
        Float32 array at ``target_sr``.
    """
    try:
        audio, sr = load_audio(data)
    except Exception:
        logger.debug("soundfile failed, falling back to ffmpeg")
        audio, sr = _load_via_ffmpeg(data)

    audio = resample(audio, sr, target_sr)
    max_samples = int(max_duration_s * target_sr)
    audio = audio[:max_samples]
    audio = normalize(audio)
    return audio.astype(np.float32)


def _load_via_ffmpeg(data: bytes) -> Tuple[np.ndarray, int]:
    """Fallback: decode webm / mp4 / ogg directly via imageio-ffmpeg executable."""
    import subprocess
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        logger.warning("imageio_ffmpeg not found, relying on system ffmpeg")
        ffmpeg_exe = "ffmpeg"

    cmd = [
        ffmpeg_exe,
        "-i", "pipe:0",           # read from stdin
        "-f", "f32le",            # output format: float 32-bit little-endian
        "-ac", "1",               # output channels: 1 (mono)
        "-ar", str(TARGET_SR),    # output sample rate
        "pipe:1"                  # write to stdout
    ]

    try:
        proc = subprocess.run(
            cmd,
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg decoding failed: {e.stderr.decode('utf-8', errors='ignore')}")
        raise RuntimeError("Failed to decode audio file")

    raw = np.frombuffer(proc.stdout, dtype=np.float32)
    # The output is directly mono f32le at TARGET_SR, so we can return as is.
    return raw, TARGET_SR


def save_temp_wav(audio: np.ndarray, path: Path, sr: int = TARGET_SR) -> None:
    """Write audio array as a 16-bit PCM WAV file."""
    sf.write(str(path), audio, sr, subtype="PCM_16")
