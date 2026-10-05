"""Enhancer service — thin wrapper around DeepFilterNet."""
from __future__ import annotations

import numpy as np
import logging
from config import settings

logger = logging.getLogger(__name__)


def enhance(audio: np.ndarray) -> np.ndarray:
    """
    Suppress background noise using DeepFilterNet.
    Returns audio unchanged when enhancement is disabled in settings.
    """
    if not settings.ENHANCE_ENABLED:
        return audio

    from models.deepfilternet.wrapper import enhance_audio

    enhanced = enhance_audio(audio, sample_rate=settings.SAMPLE_RATE)
    logger.debug("DeepFilterNet enhancement applied")
    return enhanced
