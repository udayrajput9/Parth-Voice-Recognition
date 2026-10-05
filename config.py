from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).parent
MODELS_DIR = BASE_DIR / "models"
THIRD_PARTY_DIR = BASE_DIR / "third_party"
UPLOADS_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"


class Settings(BaseSettings):
    # ── Application ───────────────────────────────────────────────────────────
    APP_NAME: str = "VoiceAuth"
    DEBUG: bool = True
    SECRET_KEY: str = "change-this-in-production-use-a-long-random-string-min-32-chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    # Short-lived token issued after password check, before voice challenge
    TEMP_TOKEN_EXPIRE_MINUTES: int = 10

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = f"sqlite:///{BASE_DIR}/voice_auth.db"

    # ── Voice Enrollment ──────────────────────────────────────────────────────
    ENROLLMENT_PARAGRAPH_LINES: int = 6
    # Minimum clear speech required to build a stable voice signature
    ENROLLMENT_MIN_SPEECH_SECONDS: float = 8.0
    SIGNIN_PASSPHRASE: str = "parth, can you give my account access"

    # ── Similarity Thresholds ─────────────────────────────────────────────────
    # Treat as starting points; calibrate empirically via EER on real pairs.
    SIMILARITY_THRESHOLD_SIGNIN: float = 0.70
    SIMILARITY_THRESHOLD_DASHBOARD: float = 0.70
    # Short utterances (1-2 words) get a slightly relaxed threshold,
    # but never below the floor — different speakers stay locked out.
    SHORT_UTTERANCE_SECONDS: float = 2.0
    SHORT_UTTERANCE_THRESHOLD_RELAX: float = 0.06
    SIMILARITY_THRESHOLD_FLOOR: float = 0.62
    # AASIST: fused bonafide probability below this → spoof detected
    ANTISPOOF_THRESHOLD: float = 0.55
    # Replay-artifact score at/above this → reject even if AASIST says bonafide
    # (AASIST-LA is blind to replayed genuine speech). Range 0-1; lower=stricter.
    REPLAY_SCORE_REJECT: float = 0.55

    # ── Challenge phrase (replay killer) ──────────────────────────────────────
    # Random words per signin, verified via Whisper ASR.  A pre-recorded clip
    # cannot contain this session's words — replay fails regardless of speaker
    # quality.  This is the primary replay defence; signal heuristics are backup.
    CHALLENGE_ENABLED: bool = True
    CHALLENGE_WORD_COUNT: int = 4
    CHALLENGE_MIN_MATCH: int = 3

    # ── Pipeline Control ──────────────────────────────────────────────────────
    # Fixed order: VAD → Antispoof → Enhance → Speaker → Similarity
    # Anti-spoof must see raw audio before enhancement.
    ANTISPOOF_ENABLED: bool = True
    VAD_ENABLED: bool = True
    ENHANCE_ENABLED: bool = True

    # ── Audio ─────────────────────────────────────────────────────────────────
    SAMPLE_RATE: int = 16000
    MAX_AUDIO_DURATION_SECONDS: int = 60
    # 1-2 spoken words (~0.4s) are enough — short-utterance handling in the
    # CAM++ wrapper (tiling) and adaptive threshold keep this safe.
    MIN_SPEECH_DURATION_SECONDS: float = 0.4

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    MAX_VOICE_ATTEMPTS: int = 5
    VOICE_LOCKOUT_MINUTES: int = 5
    MAX_LOGIN_ATTEMPTS: int = 8
    LOGIN_LOCKOUT_MINUTES: int = 5

    # ── Silero VAD ────────────────────────────────────────────────────────────
    VAD_THRESHOLD: float = 0.5
    VAD_MIN_SPEECH_MS: int = 250
    VAD_MIN_SILENCE_MS: int = 100

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
