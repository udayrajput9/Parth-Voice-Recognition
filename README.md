# VoiceAuth

**AI-powered voice biometric authentication built with FastAPI.**

Sign up by reading a paragraph aloud. Sign in by saying your passphrase. Every login is verified by your unique voice — no OTPs, no tokens, just you.

---

## Architecture

```
Browser (Mic) ──► FastAPI ──► AI Pipeline ──► SQLite DB
                               │
                    ┌──────────▼──────────┐
                    │  VAD (Silero)              │  Remove silence
                    │  Enhance (DF-Net)          │  Noise suppression
                    │  Antispoof (SSH + AASIST)  │  Liveness detection
                    │  Embed (CAM++)             │  Speaker embedding
                    │  Similarity (Cosine)       │  Identity match
                    └─────────────────────┘
```

## User Flow

```
Signup Step 1 ── Read paragraph ──► Voice signature saved
Signup Step 2 ── Fill details ────► Account created

Signin Step 1 ── Username + Password ──► Temp token issued
Signin Step 2 ── Say "PARTH" ──────────► Session cookie set

Dashboard ──► Read 100 lines ──► Terminal shows per-line result
```

---

## Prerequisites

- Python 3.10 or 3.11
- `git` installed and on PATH
- A working microphone
- (Optional) NVIDIA GPU with CUDA 11.8+ for faster inference

---

## Setup — Step by Step

### 1. Clone the project

```bash
git clone <your-repo-url> voice_auth
cd voice_auth
```

### 2. Create and activate virtual environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python -m venv venv
source venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. GPU setup (optional but recommended)

If you have an NVIDIA GPU (e.g., RTX series on Windows, or T4/A10G on Cloud VMs like AWS/Claude):

```bash
# Windows users can try the auto-script:
python scripts/setup_env.py

# Manual Setup for Cloud VMs / Linux (or if script fails):
pip uninstall onnxruntime -y
pip install onnxruntime-gpu>=1.24.1
```

> **Note for Cloud Setup:** Ensure your system has the CUDA Toolkit installed (e.g. `nvcc --version`) that matches your NVIDIA driver. The `onnxruntime-gpu` package drastically speeds up Silero VAD inference.

### 5. Clone third-party model repositories

```bash
python scripts/clone_repos.py
```

Clones into `third_party/`:
- `silero-vad` — https://github.com/snakers4/silero-vad
- `aasist` — https://github.com/clovaai/aasist
- `3D-Speaker` — https://github.com/alibaba-damo-academy/3D-Speaker

> **Note:** DeepFilterNet is installed via pip (`deepfilternet==0.5.6`) and does **not** need to be cloned. We use a built-in compatibility shim to allow it to run on newer `torchaudio >= 2.1` without crashing.

### 6. Download model weights

```bash
python scripts/download_models.py
```

| Model | File | Size |
|---|---|---|
| Silero VAD | `models/silero_vad/model.onnx` | ~1.8 MB |
| SSL+AASIST | `models/ssl_aasist/checkpoint/LA_model.pth` | ~1.2 GB |
| CAM++ | `models/campp/checkpoint/campplus.bin` | ~26 MB |
| DeepFilterNet | `models/deepfilternet/DeepFilterNet3/` | ~8 MB |

> **Note on SSL+AASIST:** The `best_SSL_model_LA.pth` (or `LA_model.pth`) file is hosted on Google Drive. If the script fails due to quota limits, you must download the folder manually using `gdown` or your browser:
> ```bash
> gdown --folder 1c4ywztEVlYVijfwbGLl9OEa1SNtFKppB -O models/ssl_aasist/checkpoint/
> ```
>
> **CAM++ Note:** If the ModelScope download fails, follow the fallback instructions printed by the script.

### 7. Configure environment

```bash
cp .env.example .env
# Edit .env — set a strong SECRET_KEY
```

### 8. Run

```bash
python main.py
# or
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Open **http://127.0.0.1:8000** in Chrome or Edge.

---

## Configuration Reference

All settings live in [`config.py`](config.py) and can be overridden via `.env`.

| Setting | Default | Description |
|---|---|---|
| `SECRET_KEY` | (change me!) | JWT signing key — use a random 32+ char string in production |
| `SIMILARITY_THRESHOLD_SIGNIN` | `0.75` | Cosine similarity cutoff for login voice challenge |
| `SIMILARITY_THRESHOLD_DASHBOARD` | `0.70` | Cosine similarity cutoff for per-line dashboard verification |
| `ANTISPOOF_THRESHOLD` | `0.5` | AASIST bonafide probability threshold |
| `ANTISPOOF_BEFORE_ENHANCE` | `False` | If `True`, runs antispoof before DeepFilterNet (see note below) |
| `ANTISPOOF_ENABLED` | `True` | Set to `False` to skip liveness detection (dev only) |
| `VAD_ENABLED` | `True` | Set to `False` to skip silence removal |
| `ENHANCE_ENABLED` | `True` | Set to `False` to skip noise suppression |
| `MAX_VOICE_ATTEMPTS` | `5` | Max failed voice challenges before lockout |
| `VOICE_LOCKOUT_MINUTES` | `15` | Lockout duration after too many failures |
| `MIN_SPEECH_DURATION_SECONDS` | `1.0` | Minimum speech detected by VAD to proceed |

### Pipeline Order Note

By default: `VAD → Enhance → Antispoof → Speaker`

Enhancement can smooth the artefacts AASIST relies on for spoofing detection. If you observe missed spoof detections, set `ANTISPOOF_BEFORE_ENHANCE=True` and compare EER on your data.

---

## Security Notes

### Fixed Passphrase Risk
The passphrase "Parth" is fixed and known. AASIST's anti-spoofing layer mitigates replay attacks, but is not infallible with recorded audio. Consider:
- Adding a **random challenge word** drawn from a small vocabulary per session
- Requiring the passphrase to be spoken within a tight time window

### Threshold Calibration
The default thresholds (0.75 / 0.70) are reasonable starting points but should be calibrated using EER (Equal Error Rate) calculated from real enrollment/test audio pairs from your target speakers.

### In-Memory Rate Limiter
`core/rate_limiter.py` uses a Python dict. This resets on server restart and does not work across multiple processes. For production, replace with a Redis-backed implementation.

---

## Project Structure

```
voice_auth/
├── main.py                    # FastAPI app entry point
├── config.py                  # All settings
├── requirements.txt
├── .env.example
│
├── database/
│   ├── db.py                  # SQLAlchemy engine
│   └── models.py              # User, VoiceSignature, AuthLog, EnrollmentSession
│
├── core/
│   ├── security.py            # JWT + bcrypt
│   └── rate_limiter.py        # Sliding-window lockout
│
├── routers/
│   ├── auth.py                # Signup, signin, logout routes
│   ├── dashboard.py           # Dashboard + per-line verification
│   └── voice.py               # Re-enrollment + health check
│
├── services/                  # AI service layer
│   ├── audio.py, vad.py, enhancer.py
│   ├── antispoof.py, speaker.py, similarity.py
│   └── pipeline.py            # Full pipeline orchestration
│
├── models/                    # Model weights + wrappers
│   ├── silero_vad/wrapper.py
│   ├── deepfilternet/wrapper.py
│   ├── aasist/wrapper.py + configs/
│   ├── campp/wrapper.py + configs/
│   └── cosine/similarity.py
│
├── third_party/               # Cloned GitHub repos
│   ├── silero-vad/
│   ├── aasist/
│   └── 3D-Speaker/
│
├── scripts/
│   ├── setup_env.py           # GPU detection + onnxruntime switch
│   ├── clone_repos.py         # Clone third_party repos
│   └── download_models.py     # Download model weights
│
├── static/css/, static/js/    # Frontend assets
└── templates/                 # Jinja2 HTML templates
```

---

## Third-Party Licenses

| Library | License |
|---|---|
| Silero VAD | MIT |
| DeepFilterNet | MIT |
| AASIST | MIT |
| 3D-Speaker / CAM++ | Apache 2.0 |
| FastAPI | MIT |
| PyTorch | BSD-3 |
