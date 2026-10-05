"""Speaker embedding service — thin wrapper around CAM++."""
from __future__ import annotations

import numpy as np
import logging

logger = logging.getLogger(__name__)


def get_embedding(audio: np.ndarray) -> np.ndarray:
    """
    Extract a 192-dim L2-normalised speaker embedding.

    Parameters
    ----------
    audio : np.ndarray
        Float32 mono 16 kHz audio.  At least 1 second recommended.

    Returns
    -------
    np.ndarray, shape (192,)
    """
    from models.campp.wrapper import extract_embedding

    emb = extract_embedding(audio)
    logger.debug("CAM++ embedding extracted, shape=%s", emb.shape)
    return emb


def get_enrollment_embedding(audio: np.ndarray, sr: int = 16000) -> np.ndarray:
    """
    Robust voice-signature embedding for enrollment.

    Long enrollment audio (the 25-line paragraph) is split into overlapping
    3-second windows; each window's embedding is extracted and the
    L2-normalised mean is stored.  Averaging over many windows cancels
    per-window noise, giving a far more stable signature than a single
    embedding of the whole clip — this is what lets short 1–2 word
    utterances at signin still match reliably.
    """
    win = 3 * sr
    hop = win // 2
    if len(audio) <= win:
        return get_embedding(audio)

    embs = []
    for start in range(0, len(audio) - win + 1, hop):
        embs.append(get_embedding(audio[start:start + win]))
    # Include the tail so no speech is wasted
    if (len(audio) - win) % hop:
        embs.append(get_embedding(audio[-win:]))

    mean = np.mean(np.stack(embs), axis=0)
    mean = mean / (np.linalg.norm(mean) + 1e-12)
    logger.debug("Enrollment embedding averaged over %d windows", len(embs))
    return mean.astype(np.float32)
