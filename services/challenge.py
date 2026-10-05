"""
Challenge-phrase service — the real defence against replay attacks.

At signin the server picks random words the user must speak.  A recording of
the user made earlier CANNOT contain this session's words, so replay fails no
matter how good the attacker's loudspeaker is.  This is how text-prompted
voice biometric systems (Siri-style) defeat replay — content verification,
not just signal forensics.

Verification is fuzzy: Whisper occasionally mis-hears one word, so we require
CHALLENGE_MIN_MATCH of the words (order-insensitive, small edit-distance
tolerance) rather than an exact transcript.
"""
from __future__ import annotations

import secrets
import logging
import numpy as np

from config import settings

logger = logging.getLogger(__name__)

# Short, phonetically distinct, easy for any accent, unambiguous for ASR.
CHALLENGE_WORDS = [
    "apple", "river", "tiger", "moon", "green", "table", "cloud", "silver",
    "candle", "window", "garden", "purple", "rocket", "mango", "ocean",
    "pencil", "yellow", "bridge", "forest", "sunny", "market", "bottle",
    "planet", "copper", "velvet", "shadow", "monkey", "castle", "orange",
    "ladder", "mirror", "basket", "thunder", "island", "cotton", "diamond",
]


def generate_challenge() -> str:
    """Return N random words, space-separated (e.g. 'tiger moon garden river')."""
    n = settings.CHALLENGE_WORD_COUNT
    idx = []
    while len(idx) < n:
        i = secrets.randbelow(len(CHALLENGE_WORDS))
        if i not in idx:
            idx.append(i)
    return " ".join(CHALLENGE_WORDS[i] for i in idx)


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein distance — tolerates small ASR mis-hearings."""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def verify_challenge(audio: np.ndarray, challenge: str) -> dict:
    """
    Transcribe ``audio`` and check the challenge words were actually spoken.

    Returns ``{passed, matched, required, transcript}``.
    """
    from models.whisper.wrapper import transcribe

    transcript = transcribe(audio)
    heard = [w.strip(".,!?;:'\"") for w in transcript.split()]

    matched = 0
    for word in challenge.lower().split():
        ok = any(
            h == word or (len(word) > 3 and _edit_distance(h, word) <= 1)
            for h in heard
        )
        if ok:
            matched += 1

    required = settings.CHALLENGE_MIN_MATCH
    passed = matched >= required
    logger.info(
        "Challenge verify: %d/%d words matched (need %d) — transcript=%r",
        matched, settings.CHALLENGE_WORD_COUNT, required, transcript,
    )
    return {
        "passed": passed,
        "matched": matched,
        "required": required,
        "transcript": transcript,
    }
