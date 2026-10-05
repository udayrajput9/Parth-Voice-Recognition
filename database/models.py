from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime,
    ForeignKey, Text, Float,
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from database.db import Base


def _now():
    return datetime.now(timezone.utc)


class User(Base):
    """Registered user account."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    full_name = Column(String(100), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)

    voice_signature = relationship(
        "VoiceSignature",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    auth_logs = relationship("AuthLog", back_populates="user")


class VoiceSignature(Base):
    """
    Speaker embedding for a user, stored as a JSON-serialised float list.
    Embedding is a 192-dim CAM++ vector, L2-normalised.
    """
    __tablename__ = "voice_signatures"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    embedding = Column(Text, nullable=False)  # JSON: [0.12, -0.34, ...]
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    user = relationship("User", back_populates="voice_signature")


class AuthLog(Base):
    """
    Immutable audit log of every authentication event.

    event_type values:
        login_attempt, login_success, login_fail,
        voice_enroll_success,
        voice_challenge_success, voice_challenge_fail, voice_spoof_detected,
        voice_locked_out,
        dashboard_line_pass, dashboard_line_fail
    """
    __tablename__ = "auth_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    username_attempt = Column(String(50), nullable=True)
    event_type = Column(String(50), nullable=False)
    similarity_score = Column(Float, nullable=True)
    antispoof_score = Column(Float, nullable=True)
    ip_address = Column(String(50), nullable=True)
    success = Column(Boolean, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)

    user = relationship("User", back_populates="auth_logs")


class EnrollmentSession(Base):
    """
    Temporary bridge between voice enrollment (Step 1) and account creation (Step 2).
    Stores the embedding until the user fills in their profile details.
    Expires after TEMP_TOKEN_EXPIRE_MINUTES.
    """
    __tablename__ = "enrollment_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_token = Column(String(255), unique=True, index=True, nullable=False)
    embedding = Column(Text, nullable=False)  # JSON-serialised
    created_at = Column(DateTime(timezone=True), default=_now)
    expires_at = Column(DateTime(timezone=True), nullable=False)
