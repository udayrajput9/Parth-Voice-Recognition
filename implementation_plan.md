# Voice-Based Authentication Module — Implementation Blueprint

## Overview

A full-stack FastAPI web application that uses AI-powered **speaker verification** as the primary authentication mechanism. Users register by reading a paragraph aloud (voice signature), and log in by speaking the passphrase **"Parth"**. After login, a real-time dashboard lets users read 100 lines of text and verifies each line against their stored voice signature.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python 3.10+) |
| Frontend | Vanilla HTML + CSS + JS (Jinja2 templates) |
| Database | SQLite (via SQLAlchemy) — easily swappable to PostgreSQL |
| Audio I/O | Browser MediaRecorder API → WAV → FastAPI endpoint |
| AI Pipeline | Silero VAD → DeepFilterNet → AASIST → CAM++ → Cosine Similarity |
| Virtual Env | `venv` (isolated, all deps pinned in requirements.txt) |

---

## User Flow

```
┌─────────────┐     ┌──────────────────────────────┐     ┌──────────────────┐
│  Landing    │────▶│  SIGNUP                      │────▶│ Fill Details     │
│  Page       │     │  1. Read paragraph aloud     │     │ (name/email/pass)│
│  /          │     │  2. Voice signature recorded │     │ /signup/details  │
│             │     │  3. Saved to DB              │     │                  │
└─────────────┘     └──────────────────────────────┘     └──────────────────┘
       │
       │
       ▼
┌─────────────┐     ┌──────────────────────────────┐     ┌──────────────────┐
│  SIGNIN     │────▶│  Voice Challenge              │────▶│  Dashboard       │
│  /signin    │     │  Say "Parth" to authenticate │     │  /dashboard      │
│  ID+Pass    │     │  voice verified against DB   │     │  Read 100 lines  │
└─────────────┘     └──────────────────────────────┘     └──────────────────┘
```

---

## Project Directory Structure

```
voice_auth/
│
├── main.py                        # FastAPI app entry point
├── config.py                      # App-wide settings (paths, thresholds)
├── requirements.txt               # All pinned dependencies
├── .env                           # Secrets (DB URL, secret key)
├── README.md
│
├── venv/                          # Python virtual environment (NOT committed)
│
├── database/
│   ├── __init__.py
│   ├── db.py                      # SQLAlchemy engine + session
│   └── models.py                  # ORM models (User, VoiceSignature)
│
├── routers/
│   ├── __init__.py
│   ├── auth.py                    # /signup, /signin, /logout routes
│   ├── voice.py                   # /voice/enroll, /voice/verify routes
│   └── dashboard.py               # /dashboard, /dashboard/verify-line
│
├── services/                      # AI pipeline wrappers
│   ├── __init__.py
│   ├── audio.py                   # Preprocessing: resample, normalize, trim
│   ├── vad.py                     # Silero VAD — Voice Activity Detection
│   ├── enhancer.py                # DeepFilterNet — Noise suppression
│   ├── antispoof.py               # AASIST — Anti-spoofing / liveness check
│   ├── speaker.py                 # CAM++ — Speaker embedding extraction
│   └── similarity.py             # Cosine Similarity — match embeddings
│
├── models/                        # Downloaded model weights + wrappers
│   ├── silero_vad/
│   │   ├── model.onnx             # Downloaded ONNX model
│   │   └── wrapper.py             # Python wrapper using onnxruntime
│   │
│   ├── deepfilternet/
│   │   ├── wrapper.py             # df.enhance() wrapper
│   │   └── configs/               # DF config files
│   │
│   ├── aasist/
│   │   ├── checkpoint/
│   │   │   └── best_model.pth     # Downloaded AASIST checkpoint
│   │   ├── configs/
│   │   │   └── AASIST.conf        # Model config
│   │   └── wrapper.py             # Inference wrapper
│   │
│   ├── campp/
│   │   ├── checkpoint/
│   │   │   └── campplus.bin       # Downloaded CAM++ weights
│   │   ├── configs/
│   │   └── wrapper.py             # Embedding extraction wrapper
│   │
│   └── cosine/
│       └── similarity.py          # torch.nn.functional.cosine_similarity
│
├── third_party/                   # Cloned GitHub repos (NOT pip-installed)
│   ├── silero-vad/                # github.com/snakers4/silero-vad
│   ├── DeepFilterNet/             # github.com/Rikorose/DeepFilterNet
│   ├── aasist/                    # github.com/clovaai/aasist
│   └── 3D-Speaker/                # github.com/alibaba-damo-academy/3D-Speaker (CAM++)
│
├── static/
│   ├── css/
│   │   ├── base.css               # Global styles, variables, fonts
│   │   ├── auth.css               # Signin/Signup page styles
│   │   └── dashboard.css          # Dashboard styles
│   ├── js/
│   │   ├── recorder.js            # MediaRecorder API wrapper
│   │   ├── signup_voice.js        # Signup voice capture logic
│   │   ├── signin_voice.js        # Signin challenge logic
│   │   └── dashboard.js           # Line-by-line reader + terminal
│   └── audio/                     # Temp audio blobs (server-side cleared)
│
├── templates/                     # Jinja2 HTML templates
│   ├── base.html
│   ├── index.html                 # Landing page
│   ├── signup_voice.html          # Step 1: Record voice signature
│   ├── signup_details.html        # Step 2: Fill name/email/password
│   ├── signin.html                # Signin: ID+Pass + voice challenge
│   └── dashboard.html             # Post-login dashboard
│
└── uploads/                       # Temporary audio uploads (auto-cleaned)
```

---

## Database Schema

### `users` table
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `username` | VARCHAR(50) | Unique |
| `email` | VARCHAR(100) | Unique |
| `hashed_password` | VARCHAR(255) | bcrypt |
| `created_at` | DATETIME | |
| `is_active` | BOOLEAN | |

### `voice_signatures` table
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `user_id` | FK → users.id | One-to-one |
| `embedding` | BLOB / TEXT | Serialized numpy array (base64 or JSON) |
| `created_at` | DATETIME | |
| `updated_at` | DATETIME | |

---

## AI Pipeline — Step by Step

```
Raw Browser Audio (WAV/WebM)
        │
        ▼
┌──────────────┐
│  audio.py    │  Resample to 16kHz mono, normalize, convert to WAV
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   vad.py     │  Silero VAD — remove silence segments
│ (model.onnx) │  → Returns speech-only audio chunks
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ enhancer.py  │  DeepFilterNet — suppress background noise
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ antispoof.py │  AASIST — detect replayed/synthetic audio
│ (best_model) │  → If spoofed: reject immediately
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  speaker.py  │  CAM++ — extract 192-dim speaker embedding
│(campplus.bin)│  → Returns embedding vector
└──────┬───────┘
       │
       ▼
┌──────────────┐
│similarity.py │  Cosine similarity vs stored embedding
└──────┬───────┘
       │
       ▼
  score ≥ threshold?
   Yes → AUTHENTICATED
   No  → REJECTED
```

---

## API Endpoints

### Auth Router `/auth`
| Method | Path | Description |
|---|---|---|
| GET | `/` | Landing page |
| GET | `/signup` | Redirect to voice enrollment |
| GET | `/signup/voice` | Voice recording page (Step 1) |
| POST | `/signup/voice/submit` | Upload enrollment audio → store embedding |
| GET | `/signup/details` | Fill name/email/password (Step 2) |
| POST | `/signup/details/submit` | Create user account |
| GET | `/signin` | Signin page |
| POST | `/signin/submit` | Verify ID+password → issue temp token for voice challenge |
| POST | `/signin/voice` | Upload "Parth" audio → verify → issue session |
| POST | `/logout` | Clear session |

### Voice Router `/voice`
| Method | Path | Description |
|---|---|---|
| POST | `/voice/enroll` | Process enrollment audio → return embedding |
| POST | `/voice/verify` | Verify audio vs stored embedding → return score + result |

### Dashboard Router `/dashboard`
| Method | Path | Description |
|---|---|---|
| GET | `/dashboard` | Load dashboard (requires session) |
| POST | `/dashboard/verify-line` | Upload line audio → verify → return result |
| GET | `/dashboard/paragraph` | Return the 100-line paragraph text |

---

## Frontend Pages

### 1. Landing Page (`/`)
- Clean hero with app name, "Sign In" and "Sign Up" buttons
- Dark glassmorphism design

### 2. Signup — Voice Enrollment (`/signup/voice`)
- Shows a 20–30 line paragraph for the user to read
- Big **"Start Recording"** button (browser mic)
- Real-time waveform visualizer while recording
- Progress indicator (lines read)
- On completion → auto-submit → redirect to details page

### 3. Signup — Fill Details (`/signup/details`)
- Simple form: Full Name, Email, Username, Password, Confirm Password
- Voice signature already stored, just filling profile info

### 4. Signin Page (`/signin`)
- Fields: Username + Password
- After submitting → Voice Challenge panel slides in
- Shows prompt: **"Say: Parth"**
- Record button → sends to API → if authenticated, redirect to dashboard

### 5. Dashboard (`/dashboard`)
**Left Panel — Paragraph Reader:**
- 100 lines of English text
- Each line has a "🎤 Read" button
- User clicks, reads the line aloud
- Line highlights while recording

**Right Panel — Terminal:**
- Dark terminal-style output box
- Each result prints: `[LINE 12] ✅ AUTHENTICATED` or `[LINE 12] ❌ NOT ALLOWED`
- Auto-scrolls to latest output
- Shows score: `Score: 0.91 | Threshold: 0.75`

---

## Requirements Strategy

### Third-party Repos (cloned, not pip-installed)
```
third_party/silero-vad/      → used via sys.path or direct import
third_party/DeepFilterNet/   → df library installed from local path
third_party/aasist/          → model code imported directly
third_party/3D-Speaker/      → CAM++ model code imported directly
```

### `requirements.txt` (pinned versions)
```
fastapi==0.111.0
uvicorn[standard]==0.29.0
python-multipart==0.0.9
jinja2==3.1.4
sqlalchemy==2.0.30
passlib[bcrypt]==1.7.4
python-jose[cryptography]==3.3.0
python-dotenv==1.0.1
numpy==1.26.4
torch==2.3.0
torchaudio==2.3.0
torchvision==0.18.0
soundfile==0.12.1
librosa==0.10.2
scipy==1.13.0
onnxruntime==1.18.0
onnxruntime-gpu==1.18.0    # if CUDA available, else remove
deepfilternet==0.5.6
aiofiles==23.2.1
httpx==0.27.0
pydantic==2.7.1
pydantic-settings==2.3.0
alembic==1.13.1
```

---

## Setup Instructions (to be documented in README)

```bash
# 1. Clone project
git clone <repo> voice_auth
cd voice_auth

# 2. Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows

# 3. Install requirements
pip install -r requirements.txt

# 4. Clone third-party repos
cd third_party
git clone https://github.com/snakers4/silero-vad
git clone https://github.com/Rikorose/DeepFilterNet
git clone https://github.com/clovaai/aasist
git clone https://github.com/alibaba-damo-academy/3D-Speaker
cd ..

# 5. Download model weights (automated script: scripts/download_models.py)
python scripts/download_models.py

# 6. Run
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## Open Questions

> [!IMPORTANT]
> **Voice Signature Enrollment**: Should the system require the user to read the **entire** 20-30 paragraph (multiple recordings averaged), or just a single clean recording? Averaging multiple embeddings gives better accuracy.

> [!IMPORTANT]
> **Similarity Threshold**: What should the cosine similarity cutoff be? Recommended: `0.75` for signin, `0.70` for line-by-line dashboard. Should this be configurable per user?

> [!IMPORTANT]
> **Database**: Use SQLite (simple, local, no server needed) or PostgreSQL? SQLite is fine for development and local deployment.

> [!IMPORTANT]
> **GPU / CPU**: Does your laptop have an NVIDIA GPU? AASIST and CAM++ will run significantly faster on CUDA. If CPU-only, inference may be slow (2–5 seconds per audio clip).

> [!WARNING]
> **AASIST checkpoint**: The `best_model.pth` must be downloaded from the official AASIST release. It is not included in the GitHub repo. A `scripts/download_models.py` will automate this.

> [!WARNING]
> **CAM++ (3D-Speaker)**: The `campplus.bin` weight file needs to be downloaded separately from ModelScope or the 3D-Speaker release page. The download script will handle this.

---

## Verification Plan

### Phase 1 — Structure Verification
- Confirm all folders, files, and third_party repos exist
- Run `python -c "import fastapi, torch, onnxruntime"` to verify installs

### Phase 2 — Service Unit Tests
- `test_vad.py` — Feed a silent + speech WAV, verify VAD output
- `test_enhancer.py` — Feed noisy WAV, verify output is cleaner
- `test_antispoof.py` — Feed real + spoofed audio, verify classification
- `test_speaker.py` — Feed two clips of same speaker, verify high similarity
- `test_similarity.py` — Verify cosine similarity math

### Phase 3 — End-to-End Flow
- Complete signup → voice enrollment → fill details
- Complete signin → voice challenge → dashboard access
- Dashboard: read lines → verify output in terminal

### Phase 4 — Browser Mic Test
- Test MediaRecorder on Chrome/Edge with laptop mic
- Verify audio quality is acceptable for model inference
