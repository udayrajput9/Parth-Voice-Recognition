"""
Voice utility router.

Routes
------
POST /voice/enroll   → Re-enroll / update voice signature (authenticated)
GET  /voice/health   → Model health check
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, Request, Depends, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import VoiceSignature, AuthLog
from routers.dashboard import get_current_user
from models.cosine.similarity import embedding_to_json
from services.pipeline import run_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/enroll")
async def re_enroll(
    request: Request,
    audio: UploadFile = File(...),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update the voice signature for the currently authenticated user.
    Useful if enrollment quality was poor.
    """
    audio_bytes = await audio.read()
    result = await run_pipeline(audio_bytes, stored_embedding_json=None)

    if result.error:
        raise HTTPException(status_code=422, detail=result.error)
    if not result.is_real:
        raise HTTPException(
            status_code=403,
            detail=f"Anti-spoofing check failed (score={result.antispoof_score:.3f}).",
        )

    embedding_json = embedding_to_json(result.embedding)

    sig = (
        db.query(VoiceSignature)
        .filter(VoiceSignature.user_id == current_user.id)
        .first()
    )
    if sig:
        sig.embedding = embedding_json
    else:
        sig = VoiceSignature(user_id=current_user.id, embedding=embedding_json)
        db.add(sig)

    log = AuthLog(
        user_id=current_user.id,
        event_type="voice_enroll_success",
        success=True,
        ip_address=request.client.host if request.client else "unknown",
        antispoof_score=result.antispoof_score,
    )
    db.add(log)
    db.commit()

    return JSONResponse(
        {
            "success": True,
            "message": "Voice signature updated successfully.",
            "antispoof_score": round(result.antispoof_score, 4),
            "duration_s": round(result.vad_duration_s, 2),
        }
    )


@router.get("/health")
async def model_health():
    """
    Check whether each AI model can be instantiated.
    Does NOT run inference — only checks imports and checkpoint files.
    """
    status = {}

    # Silero VAD
    try:
        from models.silero_vad.wrapper import MODEL_PATH
        status["vad"] = MODEL_PATH.exists()
    except Exception as e:
        status["vad"] = False
        status["vad_error"] = str(e)

    # DeepFilterNet
    try:
        import df  # noqa
        status["enhancer"] = True
    except Exception as e:
        status["enhancer"] = False
        status["enhancer_error"] = str(e)

    # SSL+AASIST
    try:
        from models.ssl_aasist.wrapper import CHECKPOINT_PATH
        status["antispoof"] = CHECKPOINT_PATH.exists()
    except Exception as e:
        status["antispoof"] = False
        status["antispoof_error"] = str(e)

    # CAM++
    try:
        from models.campp.wrapper import CHECKPOINT_PATH as CAMPP_CKPT, THIRD_PARTY_3DSPEAKER
        status["speaker"] = CAMPP_CKPT.exists() and THIRD_PARTY_3DSPEAKER.exists()
    except Exception as e:
        status["speaker"] = False
        status["speaker_error"] = str(e)

    all_ok = all(v is True for k, v in status.items() if not k.endswith("_error"))
    return JSONResponse({"all_ready": all_ok, "models": status})
