"""VAD service — thin wrapper around models/silero_vad/wrapper.py."""
from __future__ import annotations

import numpy as np
import logging
from config import settings

logger = logging.getLogger(__name__)


def apply_vad(audio: np.ndarray) -> np.ndarray:
    """
    Remove silence using Silero VAD.
    Returns audio unchanged when VAD is disabled in settings.
    """
    if not settings.VAD_ENABLED:
        return audio

    from models.silero_vad.wrapper import get_vad

    vad = get_vad(threshold=settings.VAD_THRESHOLD)
    cleaned = vad.extract_speech(audio)
    logger.debug(
        "VAD: %.2fs → %.2fs",
        len(audio) / settings.SAMPLE_RATE,
        len(cleaned) / settings.SAMPLE_RATE,
    )
    return cleaned
