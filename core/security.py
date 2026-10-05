"""
Security utilities: password hashing, JWT creation / decoding.
"""
import bcrypt
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from typing import Optional
from config import settings


# ── Password Helpers ──────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash a plain-text password using bcrypt."""
    # bcrypt spec only uses the first 72 bytes
    pw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against its bcrypt hash."""
    pw = plain.encode("utf-8")[:72]
    return bcrypt.checkpw(pw, hashed.encode("utf-8"))


# ── JWT Helpers ───────────────────────────────────────────────────────────────

def create_access_token(
    data: dict,
    expires_minutes: Optional[int] = None,
) -> str:
    """
    Create a signed JWT.

    Parameters
    ----------
    data : dict
        Payload — must include ``{"sub": username}``.
    expires_minutes : int, optional
        Override the default expiry from settings.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_temp_token(data: dict) -> str:
    """
    Short-lived token issued after password verification but before voice challenge.
    Carries ``{"sub": username, "type": "temp"}``.
    """
    payload = {**data, "type": "temp"}
    return create_access_token(payload, expires_minutes=settings.TEMP_TOKEN_EXPIRE_MINUTES)


def decode_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT.  Returns ``None`` on any error."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


def get_token_subject(token: str) -> Optional[str]:
    """Convenience: return the ``sub`` claim from a token or ``None``."""
    payload = decode_token(token)
    return payload.get("sub") if payload else None
