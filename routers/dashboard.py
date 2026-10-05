"""
Dashboard router.

Routes
------
GET  /dashboard                → Main dashboard (requires auth)
POST /dashboard/verify-line   → Verify a spoken paragraph line
GET  /dashboard/paragraph     → Return the 100-line paragraph as JSON
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from config import BASE_DIR
from database.db import get_db
from database.models import User, AuthLog
from core.security import decode_token
from services.pipeline import run_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ── 100-line English paragraph ─────────────────────────────────────────────────
PARAGRAPH_LINES = [
    "The sun rises in the east and sets in the west, marking the passage of each day.",
    "Gravity is the force that keeps planets in orbit around the sun.",
    "Water covers approximately seventy-one percent of the Earth's surface.",
    "The mitochondria are often called the powerhouse of the cell.",
    "Languages evolve over time, absorbing new words from other cultures.",
    "The speed of sound in air is approximately three hundred and forty metres per second.",
    "Forests act as carbon sinks, absorbing carbon dioxide from the atmosphere.",
    "The human heart beats around one hundred thousand times every day.",
    "Stars are massive balls of plasma held together by their own gravity.",
    "Electricity flows from areas of high potential to areas of low potential.",
    "The moon causes tides by exerting gravitational pull on the Earth's oceans.",
    "DNA carries the genetic instructions for the development of all living organisms.",
    "The Renaissance was a period of renewed interest in art, science, and philosophy.",
    "Volcanoes form where tectonic plates meet or where the crust is thin.",
    "The periodic table organises all known chemical elements by atomic number.",
    "Birds are the only living descendants of the non-avian dinosaurs.",
    "A black hole is a region of space where gravity is so strong that nothing can escape.",
    "The Internet connects billions of devices across the globe.",
    "Plants convert light energy into chemical energy through photosynthesis.",
    "The Sahara Desert is the largest hot desert in the world.",
    "Music activates nearly every area of the brain simultaneously.",
    "The first antibiotic, penicillin, was discovered accidentally by Alexander Fleming.",
    "Climate change is altering weather patterns around the world.",
    "Neurons transmit signals using a combination of electrical and chemical processes.",
    "The Roman Empire at its peak stretched across three continents.",
    "Artificial intelligence is transforming industries from healthcare to finance.",
    "Bats are the only mammals capable of sustained flight.",
    "The Arctic is warming nearly four times faster than the global average.",
    "Human speech is produced by vibrations of the vocal cords modulated by the mouth.",
    "The Nile is the longest river in the world, flowing northward through Africa.",
    "Quantum computers use qubits that can represent both zero and one simultaneously.",
    "The Great Wall of China was built over many centuries to defend against invasions.",
    "Sound travels faster through water than through air.",
    "The ozone layer protects life on Earth from harmful ultraviolet radiation.",
    "Cells are the basic structural and functional units of all living organisms.",
    "Renewable energy sources include solar, wind, hydro, and geothermal power.",
    "The speed of a computer processor is measured in gigahertz.",
    "Elephants have the largest brains of any land animal.",
    "The discovery of fire allowed early humans to cook food and stay warm.",
    "Satellites orbit the Earth at various altitudes depending on their purpose.",
    "Chemical reactions involve the breaking and forming of bonds between atoms.",
    "The Industrial Revolution began in Britain in the eighteenth century.",
    "Spiders produce silk that is stronger than steel by weight.",
    "Plate tectonics explains why continents slowly drift across the Earth's surface.",
    "The human genome contains approximately three billion base pairs of DNA.",
    "Light bends when it passes from one medium to another, a phenomenon called refraction.",
    "The Amazon River discharges more water than any other river on Earth.",
    "Computers process instructions in binary, using sequences of zeros and ones.",
    "The Taj Mahal was built by Emperor Shah Jahan in memory of his wife.",
    "Vaccines work by training the immune system to recognise specific pathogens.",
    "The stratosphere contains most of the atmosphere's ozone.",
    "Dolphins communicate using a complex system of clicks and whistles.",
    "The first programmable electronic computer was ENIAC, built in nineteen forty-five.",
    "Ocean currents regulate the climate by distributing heat around the planet.",
    "The theory of relativity was developed by Albert Einstein in the early twentieth century.",
    "Photons are particles of light that travel at the speed of light in a vacuum.",
    "The digestive system breaks down food into nutrients the body can absorb.",
    "Polar ice reflects sunlight back into space, helping to regulate global temperature.",
    "The printing press made books affordable and literacy rates increased dramatically.",
    "Neural networks are loosely inspired by the structure of the human brain.",
    "The Himalayas were formed by the collision of the Indian and Eurasian tectonic plates.",
    "Rainforests are home to more than half of the world's plant and animal species.",
    "The transistor revolutionised electronics and made modern computers possible.",
    "Osmosis is the movement of water through a semi-permeable membrane.",
    "The Great Pyramid of Giza is the oldest of the Seven Wonders of the Ancient World.",
    "Radio waves, microwaves, and visible light are all forms of electromagnetic radiation.",
    "Bacteria are single-celled organisms found in nearly every environment on Earth.",
    "The first humans to walk on the moon were Neil Armstrong and Buzz Aldrin.",
    "Coral reefs are sometimes called the rainforests of the sea.",
    "The cerebral cortex is responsible for higher-order thinking and decision-making.",
    "Wind energy harnesses the kinetic energy of moving air to generate electricity.",
    "The invention of writing allowed humans to preserve knowledge across generations.",
    "Insects are the most diverse group of animals on the planet.",
    "The Milky Way contains between one hundred and four hundred billion stars.",
    "Economic growth is often measured by changes in gross domestic product.",
    "The lymphatic system helps defend the body against infection and disease.",
    "Glass is made by melting sand, soda ash, and limestone at high temperatures.",
    "The first Olympic Games were held in ancient Greece in seven seventy-six BCE.",
    "Hurricanes are powered by the warm surface waters of tropical oceans.",
    "The Wright brothers achieved the first powered flight in nineteen oh three.",
    "Superconductors conduct electricity with zero resistance at very low temperatures.",
    "The study of ancient human societies through artefacts is called archaeology.",
    "Capillary action allows water to rise through narrow tubes against gravity.",
    "The Blue Whale is the largest animal known to have ever existed on Earth.",
    "Blockchain is a decentralised ledger that records transactions across many computers.",
    "Photovoltaic cells convert sunlight directly into electrical energy.",
    "The French Revolution began in seventeen eighty-nine and ended the monarchy.",
    "Sound is a mechanical wave that requires a medium to travel through.",
    "The cerebellum coordinates voluntary movements and helps maintain balance.",
    "Biodiversity refers to the variety of life forms within a given ecosystem.",
    "Radiocarbon dating can determine the age of organic materials up to fifty thousand years old.",
    "The human eye can distinguish approximately ten million different colours.",
    "Chess is believed to have originated in India around the sixth century CE.",
    "Erosion gradually shapes landscapes by wearing away rock and soil over time.",
    "Machine learning algorithms improve their performance automatically through experience.",
    "The deepest point in the ocean is the Challenger Deep in the Mariana Trench.",
    "Thermodynamics describes how energy is transferred and transformed in physical systems.",
    "The invention of the telephone by Alexander Graham Bell changed human communication forever.",
]


# ── Auth dependency ────────────────────────────────────────────────────────────

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """
    FastAPI dependency: decode the access_token cookie and return the current user.
    Redirects to signin if the token is missing, invalid, or the user doesn't exist.
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=302, headers={"Location": "/auth/signin"})

    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=302, headers={"Location": "/auth/signin"})

    username = payload.get("sub")
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/auth/signin"})

    return user


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Render the main dashboard."""
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "current_user": current_user,
            "paragraph_lines": PARAGRAPH_LINES,
        },
    )


@router.post("/verify-line")
async def verify_line(
    request: Request,
    audio: UploadFile = File(...),
    line_number: int = Form(...),
    line_text: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Verify a spoken line against the user's stored voice signature.
    Returns JSON with the verification result and scores.
    """
    if not current_user.voice_signature:
        return JSONResponse(
            {"success": False, "error": "No voice signature found for this user."},
            status_code=400,
        )

    audio_bytes = await audio.read()
    result = await run_pipeline(
        audio_bytes,
        stored_embedding_json=current_user.voice_signature.embedding,
        mode="dashboard",
    )

    # Determine event type for logging
    if not result.is_real:
        event_type = "dashboard_line_fail"
        success = False
    elif result.authenticated:
        event_type = "dashboard_line_pass"
        success = True
    else:
        event_type = "dashboard_line_fail"
        success = False

    # Audit log
    ip = request.client.host if request.client else "unknown"
    log = AuthLog(
        user_id=current_user.id,
        event_type=event_type,
        success=success,
        ip_address=ip,
        similarity_score=result.similarity_score,
        antispoof_score=result.antispoof_score,
    )
    db.add(log)
    db.commit()

    return JSONResponse(
        {
            "line_number": line_number,
            "authenticated": result.authenticated,
            "score": result.similarity_score,
            "threshold": result.threshold,
            "antispoof_score": result.antispoof_score,
            "is_real": result.is_real,
            "vad_duration_s": round(result.vad_duration_s, 2),
            "error": result.error,
        }
    )


@router.get("/paragraph")
async def get_paragraph(current_user: User = Depends(get_current_user)):
    """Return the full 100-line paragraph as JSON."""
    return JSONResponse({"lines": PARAGRAPH_LINES})
