"""Anti-spoofing service — SSL+AASIST fused with a replay-artifact detector.

SSL+AASIST (trained on ASVspoof LA) is strong against TTS / voice conversion,
but weak against *replay* attacks — a genuine recording played back through a
loudspeaker is still a genuine human voice, so the LA model happily accepts it.

Replay, however, leaves physical traces that live capture does not:

  1. Low-band loss     — small loudspeakers cannot reproduce < 150 Hz; a live
                         close mic picks up strong breath/plosive energy there.
  2. High-band loss    — speaker + room + re-recording rolls off 6–8 kHz.
  3. Raised noise floor— playback device hiss + room tone lifts the quietest
                         frames relative to the loudest (compressed dynamics).
  4. Modulation smear  — speaker→air→mic adds reverb that blurs the crisp
                         2–8 Hz syllabic modulation of live close-talk speech.

Each cue is scored continuously in [0, 1]; the weighted sum is the replay
score.  One weak cue never rejects a genuine user — it takes multiple cues
agreeing.  All checks run on RAW pre-VAD, pre-enhancement audio: VAD and
DeepFilterNet would strip exactly these artefacts.
"""
from __future__ import annotations

import numpy as np
import logging
from typing import Tuple
from config import settings

logger = logging.getLogger(__name__)


def _frame_rms(audio: np.ndarray, frame: int = 160) -> np.ndarray:
    """Per-10ms-frame RMS energy envelope (at 16 kHz)."""
    n = len(audio) // frame
    if n == 0:
        return np.array([0.0])
    x = audio[: n * frame].reshape(n, frame)
    return np.sqrt(np.mean(x ** 2, axis=1) + 1e-12)


def replay_score(audio: np.ndarray, sr: int = 16000) -> float:
    """Return a replay-likelihood score in [0, 1].  Higher = more replay-like."""
    if len(audio) < sr:  # < 1 s: not enough signal to judge
        return 0.0

    spec = np.abs(np.fft.rfft(audio * np.hanning(len(audio)))) ** 2
    freqs = np.fft.rfftfreq(len(audio), d=1.0 / sr)
    total = float(np.sum(spec)) + 1e-12

    def band(lo: float, hi: float) -> float:
        return float(np.sum(spec[(freqs >= lo) & (freqs < hi)])) / total

    # ── Cue 1: sub-150 Hz energy (live close-mic speech has plenty) ──────────
    r_low = band(20, 150)
    s_low = float(np.clip((0.015 - r_low) / 0.015, 0.0, 1.0))

    # ── Cue 2: 6–8 kHz energy relative to the speech band ────────────────────
    mid = band(300, 3400) + 1e-12
    r_high = band(6000, 7800) / mid
    s_high = float(np.clip((0.006 - r_high) / 0.006, 0.0, 1.0))

    # ── Cue 3: noise floor / compressed dynamics ─────────────────────────────
    env = _frame_rms(audio)
    p10, p90 = np.percentile(env, 10), np.percentile(env, 90)
    floor_ratio = float(p10 / (p90 + 1e-12))
    # Live quiet-room capture: ~0.01–0.08.  Playback hiss pushes this up.
    s_floor = float(np.clip((floor_ratio - 0.08) / 0.20, 0.0, 1.0))

    # ── Cue 4: syllabic modulation depth (reverb smears it) ──────────────────
    env_n = env / (np.mean(env) + 1e-12)
    mod = np.abs(np.fft.rfft(env_n - np.mean(env_n))) ** 2
    mod_f = np.fft.rfftfreq(len(env_n), d=0.01)  # envelope at 100 fps
    mod_total = float(np.sum(mod[(mod_f >= 0.5) & (mod_f <= 25)])) + 1e-12
    mod_syll = float(np.sum(mod[(mod_f >= 2) & (mod_f <= 8)])) / mod_total
    # Live speech: typically > 0.45; heavy reverb/replay drifts lower.
    s_mod = float(np.clip((0.35 - mod_syll) / 0.35, 0.0, 1.0))

    # Weights sum to > 1 on purpose: any TWO strong cues agreeing push the
    # score past the reject gate, while one cue alone tops out just below it
    # (a single cue can be hardware quirk — e.g. laptop mics high-pass < 150 Hz).
    score = 0.50 * s_low + 0.45 * s_high + 0.40 * s_floor + 0.40 * s_mod
    logger.debug(
        "replay cues: low=%.2f high=%.2f floor=%.2f mod=%.2f → score=%.3f",
        s_low, s_high, s_floor, s_mod, score,
    )
    return float(np.clip(score, 0.0, 1.0))


def check_liveness(audio: np.ndarray) -> Tuple[float, bool]:
    """
    Detect whether audio is real (bonafide) or synthetic/replayed.

    Must be called with RAW pre-VAD, pre-enhancement audio.

    Returns
    -------
    score : float
        Fused bonafide probability in [0, 1].
    is_real : bool
        True if audio passes both the AASIST check and the replay check.
    """
    if not settings.ANTISPOOF_ENABLED:
        logger.debug("Anti-spoofing disabled — passing all audio")
        return 1.0, True

    from models.ssl_aasist.wrapper import check_liveness as predict

    aasist_score, _ = predict(audio)
    replay = replay_score(audio, sr=settings.SAMPLE_RATE)

    # Multiplicative fusion: a confident AASIST score survives one weak replay
    # cue, but multiple agreeing cues pull the fused score under the threshold.
    fused = aasist_score * (1.0 - replay)

    # Hard gate: strongly replay-like audio is rejected no matter what the
    # LA model thinks — replay is exactly its blind spot.
    replay_reject = replay >= settings.REPLAY_SCORE_REJECT
    is_real = (fused >= settings.ANTISPOOF_THRESHOLD) and not replay_reject

    logger.info(
        "Antispoof: aasist=%.4f replay=%.3f fused=%.4f reject_gate=%s is_real=%s",
        aasist_score, replay, fused, replay_reject, is_real,
    )
    return fused, is_real
