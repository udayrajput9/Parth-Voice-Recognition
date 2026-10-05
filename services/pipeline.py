"""
Full voice authentication pipeline.

Pipeline order (fixed — security-critical):

  bytes → preprocess → VAD → Antispoof → Enhance → Speaker embedding → Similarity

Design rationale
----------------
Anti-spoof (SSL+AASIST) MUST run on the raw / VAD-cleaned audio, **before**
enhancement.  DeepFilterNet smooths exactly the artefacts AASIST relies on to
detect synthetic / replayed audio.  If anti-spoof ran after enhancement, a
recorded or TTS-generated clip could slip through undetected.

Enhancement is only applied to improve the speaker embedding quality (CAM++),
where cleaner audio → better cosine similarity.

This matches what banking-grade voice biometric systems do:
  1. Liveness / anti-spoof on raw signal
  2. Clean audio only for speaker verification
"""
from __future__ import annotations

import numpy as np
import logging
from dataclasses import dataclass, field
from typing import Optional

from config import settings
from services.audio import preprocess_bytes
from services.vad import apply_vad
from services.enhancer import enhance
from services.antispoof import check_liveness
from services.speaker import get_embedding, get_enrollment_embedding
from services.similarity import compare

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Structured result returned by :func:`run_pipeline`."""

    # Anti-spoofing
    antispoof_score: float
    is_real: bool

    # Speaker embedding (None when spoofed — pipeline aborts early)
    embedding: Optional[np.ndarray]

    # Similarity (None when no stored embedding is provided → enrolment mode)
    similarity_score: Optional[float]
    threshold: Optional[float]
    authenticated: Optional[bool]

    # Diagnostics
    vad_duration_s: float

    # Human-readable error (set when the pipeline rejects the audio)
    error: Optional[str] = None


async def run_pipeline(
    audio_bytes: bytes,
    stored_embedding_json: Optional[str] = None,
    mode: str = "signin",
) -> PipelineResult:
    """
    Run the complete voice authentication pipeline.

    Parameters
    ----------
    audio_bytes : bytes
        Raw audio bytes from the browser MediaRecorder API.
    stored_embedding_json : str or None
        JSON string of the stored embedding from the database.
        Pass ``None`` for enrolment (returns embedding without comparing).
    mode : str
        ``"signin"`` or ``"dashboard"`` — controls the similarity threshold.

    Returns
    -------
    PipelineResult
    """
    # ── Step 1: Preprocess ────────────────────────────────────────────────────
    audio = preprocess_bytes(
        audio_bytes,
        target_sr=settings.SAMPLE_RATE,
        max_duration_s=settings.MAX_AUDIO_DURATION_SECONDS,
    )

    # Keep the pre-VAD signal for anti-spoofing: replay/spoof artefacts live in
    # the silences and the noise floor, which VAD strips out.  AASIST was also
    # trained on full utterances that include silence.
    raw_audio = audio

    # ── Step 2: VAD ───────────────────────────────────────────────────────────
    if settings.VAD_ENABLED:
        audio = apply_vad(audio)
    vad_duration = len(audio) / settings.SAMPLE_RATE

    if vad_duration < settings.MIN_SPEECH_DURATION_SECONDS:
        return PipelineResult(
            antispoof_score=0.0,
            is_real=False,
            embedding=None,
            similarity_score=None,
            threshold=None,
            authenticated=False,
            vad_duration_s=vad_duration,
            error=(
                f"Too little speech detected ({vad_duration:.1f}s < "
                f"{settings.MIN_SPEECH_DURATION_SECONDS}s). "
                "Please speak louder or move closer to the microphone."
            ),
        )

    # ── Step 3: Anti-spoof (on RAW / VAD-cleaned audio) ───────────────────────
    # IMPORTANT: This MUST run BEFORE enhancement.  Enhancement smooths the
    # artefacts that AASIST uses to detect spoofed / replayed audio.
    antispoof_score, is_real = 1.0, True

    if settings.ANTISPOOF_ENABLED:
        antispoof_score, is_real = check_liveness(raw_audio)
        if not is_real:
            return PipelineResult(
                antispoof_score=antispoof_score,
                is_real=False,
                embedding=None,
                similarity_score=None,
                threshold=None,
                authenticated=False,
                vad_duration_s=vad_duration,
                error="Spoofed audio detected. Only real speech is accepted.",
            )

    # ── Step 4: Enhancement (only for speaker embedding quality) ──────────────
    if settings.ENHANCE_ENABLED:
        audio = enhance(audio)

    # ── Step 5: Speaker Embedding ─────────────────────────────────────────────
    # Enrolment: average embeddings over overlapping windows → stable signature.
    if stored_embedding_json is None:
        embedding = get_enrollment_embedding(audio, sr=settings.SAMPLE_RATE)
        return PipelineResult(
            antispoof_score=antispoof_score,
            is_real=is_real,
            embedding=embedding,
            similarity_score=None,
            threshold=None,
            authenticated=None,  # not applicable in enrolment
            vad_duration_s=vad_duration,
        )

    embedding = get_embedding(audio)

    # ── Step 6: Similarity ────────────────────────────────────────────────────
    result = compare(
        embedding, stored_embedding_json, mode=mode, speech_duration_s=vad_duration
    )
    return PipelineResult(
        antispoof_score=antispoof_score,
        is_real=is_real,
        embedding=embedding,
        similarity_score=result["score"],
        threshold=result["threshold"],
        authenticated=result["authenticated"],
        vad_duration_s=vad_duration,
    )

