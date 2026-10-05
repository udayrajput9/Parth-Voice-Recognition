"""Similarity service — compares embeddings and applies threshold."""
from __future__ import annotations

import numpy as np
from models.cosine.similarity import cosine_similarity, json_to_embedding
from config import settings


def compare(
    embedding: np.ndarray,
    stored_json: str,
    mode: str = "signin",
    speech_duration_s: float | None = None,
) -> dict:
    """
    Compare a fresh embedding against a stored one.

    Parameters
    ----------
    embedding : np.ndarray
        Freshly extracted embedding.
    stored_json : str
        JSON string of the stored embedding (from DB).
    mode : str
        ``"signin"`` or ``"dashboard"`` — selects the similarity threshold.

    Returns
    -------
    dict
        ``{score, threshold, authenticated}``
    """
    stored = json_to_embedding(stored_json)
    score = cosine_similarity(embedding, stored)
    threshold = (
        settings.SIMILARITY_THRESHOLD_SIGNIN
        if mode == "signin"
        else settings.SIMILARITY_THRESHOLD_DASHBOARD
    )
    # Short utterances (1–2 words) carry less speaker information, so genuine
    # scores drop.  Relax the threshold slightly — never below the floor, so a
    # different speaker still cannot get in.
    if speech_duration_s is not None and speech_duration_s < settings.SHORT_UTTERANCE_SECONDS:
        threshold = max(
            settings.SIMILARITY_THRESHOLD_FLOOR,
            threshold - settings.SHORT_UTTERANCE_THRESHOLD_RELAX,
        )
    return {
        "score": round(score, 4),
        "threshold": threshold,
        "authenticated": bool(score >= threshold),
    }
