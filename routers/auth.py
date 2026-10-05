"""
Authentication router.

Routes
------
GET  /auth/                         → Landing page
GET  /auth/signup/voice             → Step 1: Voice enrollment page
POST /auth/signup/voice/submit      → Process enrollment audio
GET  /auth/signup/details           → Step 2: Fill account details
POST /auth/signup/details/submit    → Create user account
GET  /auth/signin                   → Signin page
POST /auth/signin/submit            → Verify credentials → issue temp token
POST /auth/signin/voice             → Verify voice → issue session cookie
GET  /auth/logout                   → Clear session → redirect to /
"""
from __future__ import annotations

import secrets
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import (
    APIRouter, Request, Depends, Form, UploadFile, File,
    Response, HTTPException,
)
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from config import settings, BASE_DIR
from database.db import get_db
from database.models import User, VoiceSignature, EnrollmentSession, AuthLog
from core.security import (
    hash_password, verify_password,
    create_access_token, create_temp_token, decode_token,
)
from core.rate_limiter import login_limiter, voice_limiter
from models.cosine.similarity import embedding_to_json
from services.pipeline import run_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ── Enrollment sentences ──────────────────────────────────────────────────────
# 6 short, phonetically rich sentences (~25 s of speech total).  Together they
# cover all English vowels and most consonant clusters, which is what the
# speaker embedding needs — reading more text adds time, not accuracy.
# The pipeline averages embeddings over overlapping windows, so ~20 s of
# clean speech already yields a stable voice signature.
ENROLLMENT_PARAGRAPH = [
    "The quick brown fox jumps over the lazy dog near the riverbank.",
    "My voice is my password, and it opens every door I own.",
    "Bright blue birds fly above the green mountain meadows in June.",
    "She sells seashells and fresh orange juice by the seashore.",
    "Technology should feel simple, secure, and made just for you.",
    "Zero, one, two, three, four, five, six, seven, eight, nine.",
]


def _get_client_ip(request: Request) -> str:
    """Extract client IP from X-Forwarded-For or direct connection."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _log_event(
    db: Session,
    event_type: str,
    success: bool,
    ip: str,
    user: User | None = None,
    username_attempt: str | None = None,
    similarity_score: float | None = None,
    antispoof_score: float | None = None,
) -> None:
    """Write an immutable AuthLog entry."""
    entry = AuthLog(
        user_id=user.id if user else None,
        username_attempt=username_attempt or (user.username if user else None),
        event_type=event_type,
        success=success,
        ip_address=ip,
        similarity_score=similarity_score,
        antispoof_score=antispoof_score,
    )
    db.add(entry)
    db.commit()


# ── Landing page ──────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ── Signup Step 1: Voice Enrollment ──────────────────────────────────────────

@router.get("/signup/voice", response_class=HTMLResponse)
async def signup_voice_page(request: Request):
    """Render the voice enrollment page."""
    return templates.TemplateResponse(
        "signup_voice.html",
        {
            "request": request,
            "paragraph_lines": ENROLLMENT_PARAGRAPH,
        },
    )


@router.post("/signup/voice/submit")
async def signup_voice_submit(
    request: Request,
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Process enrollment audio.
    Returns JSON with a one-time enrollment token the client passes to Step 2.
    """
    audio_bytes = await audio.read()
    result = await run_pipeline(audio_bytes, stored_embedding_json=None)

    if result.error:
        raise HTTPException(status_code=422, detail=result.error)

    if not result.is_real:
        raise HTTPException(
            status_code=403,
            detail=f"Anti-spoofing check failed (score={result.antispoof_score:.3f}). "
                   "Please use your real voice.",
        )

    # Enrollment needs more speech than signin — the signature must be stable.
    if result.vad_duration_s < settings.ENROLLMENT_MIN_SPEECH_SECONDS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Only {result.vad_duration_s:.1f}s of clear speech detected — "
                f"at least {settings.ENROLLMENT_MIN_SPEECH_SECONDS:.0f}s is needed. "
                "Please read all the sentences at a normal pace."
            ),
        )

    # Simple quality rating shown to the user (based on usable speech length)
    if result.vad_duration_s >= 20:
        quality = "excellent"
    elif result.vad_duration_s >= 14:
        quality = "good"
    else:
        quality = "okay"

    # Store embedding in a temporary EnrollmentSession
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.TEMP_TOKEN_EXPIRE_MINUTES
    )
    session = EnrollmentSession(
        session_token=token,
        embedding=embedding_to_json(result.embedding),
        expires_at=expires_at,
    )
    db.add(session)
    db.commit()

    logger.info("Voice enrollment successful — token issued")
    return JSONResponse(
        {
            "success": True,
            "token": token,
            "duration_s": round(result.vad_duration_s, 2),
            "quality": quality,
            "antispoof_score": round(result.antispoof_score, 4),
        }
    )


# ── Signup Step 2: Fill Account Details ──────────────────────────────────────

@router.get("/signup/details", response_class=HTMLResponse)
async def signup_details_page(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
):
    """Render the account-creation form.  Validates the enrollment token first."""
    now = datetime.now(timezone.utc)
    session = (
        db.query(EnrollmentSession)
        .filter(
            EnrollmentSession.session_token == token,
            EnrollmentSession.expires_at > now,
        )
        .first()
    )
    if not session:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": "Enrollment session expired or invalid. Please start again.",
            },
            status_code=400,
        )

    return templates.TemplateResponse(
        "signup_details.html",
        {"request": request, "enrollment_token": token},
    )


@router.post("/signup/details/submit")
async def signup_details_submit(
    request: Request,
    response: Response,
    full_name: str = Form(...),
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    enrollment_token: str = Form(...),
    db: Session = Depends(get_db),
):
    """Create the user account and persist the voice signature."""
    # ── Validate enrollment session ───────────────────────────────────────────
    now = datetime.now(timezone.utc)
    enroll_session = (
        db.query(EnrollmentSession)
        .filter(
            EnrollmentSession.session_token == enrollment_token,
            EnrollmentSession.expires_at > now,
        )
        .first()
    )
    if not enroll_session:
        return JSONResponse(
            {"success": False, "error": "Enrollment session expired. Please re-record your voice."},
            status_code=400,
        )

    # ── Validate form fields ──────────────────────────────────────────────────
    errors = {}
    if len(password) < 8:
        errors["password"] = "Password must be at least 8 characters."
    if password != confirm_password:
        errors["confirm_password"] = "Passwords do not match."
    if db.query(User).filter(User.username == username).first():
        errors["username"] = "Username already taken."
    if db.query(User).filter(User.email == email).first():
        errors["email"] = "Email already registered."

    if errors:
        return JSONResponse({"success": False, "errors": errors}, status_code=422)

    # ── Create user ───────────────────────────────────────────────────────────
    user = User(
        username=username,
        email=email,
        full_name=full_name,
        hashed_password=hash_password(password),
    )
    db.add(user)
    db.flush()  # get user.id before committing

    # ── Save voice signature ──────────────────────────────────────────────────
    sig = VoiceSignature(user_id=user.id, embedding=enroll_session.embedding)
    db.add(sig)

    # ── Clean up enrollment session ───────────────────────────────────────────
    db.delete(enroll_session)
    db.commit()

    # ── Issue session cookie ──────────────────────────────────────────────────
    token = create_access_token({"sub": user.username})
    _log_event(db, "voice_enroll_success", True, _get_client_ip(request), user=user)

    resp = JSONResponse({"success": True, "redirect": "/dashboard"})
    resp.set_cookie(
        "access_token",
        token,
        httponly=True,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return resp


# ── Signin ────────────────────────────────────────────────────────────────────

@router.get("/signin", response_class=HTMLResponse)
async def signin_page(request: Request):
    return templates.TemplateResponse("signin.html", {"request": request})


@router.post("/signin/submit")
async def signin_submit(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Step 1 of signin: verify username + password.
    Returns a short-lived temp_token for the voice challenge step.
    """
    body = await request.json()
    username = body.get("username", "").strip()
    password = body.get("password", "")
    ip = _get_client_ip(request)

    # Rate limit
    if login_limiter.is_locked(ip):
        remaining = login_limiter.lockout_remaining_seconds(ip)
        return JSONResponse(
            {"success": False, "error": f"Too many attempts. Try again in {remaining}s."},
            status_code=429,
        )

    user = db.query(User).filter(User.username == username).first()

    if not user or not verify_password(password, user.hashed_password):
        login_limiter.record_failure(ip)
        _log_event(db, "login_fail", False, ip, username_attempt=username)
        remaining = login_limiter.remaining_attempts(ip)
        return JSONResponse(
            {
                "success": False,
                "error": "Invalid username or password.",
                "remaining_attempts": remaining,
            },
            status_code=401,
        )

    if not user.is_active:
        return JSONResponse(
            {"success": False, "error": "Account is disabled."},
            status_code=403,
        )

    if not user.voice_signature:
        return JSONResponse(
            {"success": False, "error": "No voice signature found. Please sign up first."},
            status_code=403,
        )

    login_limiter.record_success(ip)
    _log_event(db, "login_success", True, ip, user=user)

    # Random challenge words baked into the SIGNED temp token: the client
    # can display them but cannot tamper with them.
    challenge = None
    if settings.CHALLENGE_ENABLED:
        from services.challenge import generate_challenge
        challenge = generate_challenge()

    temp_token = create_temp_token(
        {"sub": user.username, "type": "temp", "challenge": challenge}
    )
    return JSONResponse(
        {"success": True, "temp_token": temp_token, "challenge": challenge}
    )


@router.post("/signin/voice")
async def signin_voice(
    request: Request,
    audio: UploadFile = File(...),
    temp_token: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    Step 2 of signin: voice challenge.
    User must say the passphrase "Parth".
    """
    ip = _get_client_ip(request)

    # Decode temp token
    payload = decode_token(temp_token)
    if not payload or payload.get("type") != "temp":
        raise HTTPException(status_code=401, detail="Invalid or expired session token.")

    username = payload.get("sub")
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.voice_signature:
        raise HTTPException(status_code=401, detail="User not found.")

    # Rate limit per user
    if voice_limiter.is_locked(username):
        remaining = voice_limiter.lockout_remaining_seconds(username)
        _log_event(db, "voice_locked_out", False, ip, user=user)
        return JSONResponse(
            {"success": False, "error": f"Too many failed voice attempts. Try again in {remaining}s."},
            status_code=429,
        )

    audio_bytes = await audio.read()
    result = await run_pipeline(
        audio_bytes,
        stored_embedding_json=user.voice_signature.embedding,
        mode="signin",
    )

    # Spoof detected
    if not result.is_real:
        voice_limiter.record_failure(username)
        _log_event(
            db, "voice_spoof_detected", False, ip, user=user,
            antispoof_score=result.antispoof_score,
        )
        return JSONResponse(
            {
                "success": False,
                "error": "Spoofed audio detected. Use your real voice.",
                "antispoof_score": result.antispoof_score,
            },
            status_code=403,
        )

    # Pipeline error (insufficient speech, etc.)
    if result.error:
        return JSONResponse({"success": False, "error": result.error}, status_code=422)

    # Challenge phrase: the words for THIS signin must actually be spoken.
    # This is the replay killer — an old recording can't contain them.
    challenge = payload.get("challenge")
    if settings.CHALLENGE_ENABLED and challenge:
        from services.challenge import verify_challenge
        from services.audio import preprocess_bytes

        asr_audio = preprocess_bytes(
            audio_bytes,
            target_sr=settings.SAMPLE_RATE,
            max_duration_s=settings.MAX_AUDIO_DURATION_SECONDS,
        )
        chal = verify_challenge(asr_audio, challenge)
        if not chal["passed"]:
            voice_limiter.record_failure(username)
            _log_event(
                db, "voice_challenge_words_fail", False, ip, user=user,
                antispoof_score=result.antispoof_score,
            )
            return JSONResponse(
                {
                    "success": False,
                    "error": (
                        f"Challenge words not detected ({chal['matched']}/"
                        f"{settings.CHALLENGE_WORD_COUNT} heard, need {chal['required']}). "
                        "Speak the words shown on screen — recordings won't work."
                    ),
                },
                status_code=403,
            )

    # Voice not recognised
    if not result.authenticated:
        locked = voice_limiter.record_failure(username)
        _log_event(
            db, "voice_challenge_fail", False, ip, user=user,
            similarity_score=result.similarity_score,
            antispoof_score=result.antispoof_score,
        )
        remaining = voice_limiter.remaining_attempts(username)
        msg = "Voice not recognised."
        if locked:
            msg = f"Too many failed attempts. Account locked for {settings.VOICE_LOCKOUT_MINUTES} minutes."
        return JSONResponse(
            {
                "success": False,
                "error": msg,
                "score": result.similarity_score,
                "threshold": result.threshold,
                "remaining_attempts": remaining,
            },
            status_code=401,
        )

    # Authenticated
    voice_limiter.record_success(username)
    _log_event(
        db, "voice_challenge_success", True, ip, user=user,
        similarity_score=result.similarity_score,
        antispoof_score=result.antispoof_score,
    )

    access_token = create_access_token({"sub": username})
    resp = JSONResponse(
        {
            "success": True,
            "score": result.similarity_score,
            "threshold": result.threshold,
            "redirect": "/dashboard",
        }
    )
    resp.set_cookie(
        "access_token",
        access_token,
        httponly=True,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return resp


# ── Logout ────────────────────────────────────────────────────────────────────

@router.get("/logout")
async def logout():
    resp = RedirectResponse(url="/auth/", status_code=302)
    resp.delete_cookie("access_token")
    return resp
