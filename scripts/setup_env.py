#!/usr/bin/env python
"""
setup_env.py — Environment setup script.

Detects whether an NVIDIA GPU is available and installs the correct
onnxruntime variant.  Also creates a .env file from .env.example if
one does not yet exist.

Usage:
    python scripts/setup_env.py
"""
from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path

ROOT = Path(__file__).parent.parent


# ── GPU detection ─────────────────────────────────────────────────────────────

def check_cuda() -> bool:
    """Return True if an NVIDIA GPU with CUDA is available."""
    # Method 1: nvidia-smi
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            print("✅ nvidia-smi found — NVIDIA GPU detected")
            print(result.stdout.split("\n")[0])  # print first line (driver info)
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Method 2: torch (if already installed)
    try:
        import torch
        if torch.cuda.is_available():
            print(f"✅ torch.cuda.is_available() = True  ({torch.cuda.get_device_name(0)})")
            return True
    except ImportError:
        pass

    print("ℹ️  No NVIDIA GPU detected — using CPU")
    return False


# ── onnxruntime install ────────────────────────────────────────────────────────

def install_onnxruntime_gpu() -> None:
    print("\n🔄  Switching to onnxruntime-gpu...")
    # Uninstall CPU version first (they share the same namespace)
    subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "onnxruntime", "-y"],
        check=False,
    )
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "onnxruntime-gpu>=1.24.1"],
        check=True,
    )
    print("✅  onnxruntime-gpu>=1.24.1 installed")


def install_onnxruntime_cpu() -> None:
    print("\n🔄  Ensuring onnxruntime (CPU) is installed...")
    # Remove GPU version if present
    subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "onnxruntime-gpu", "-y"],
        check=False,
    )
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "onnxruntime>=1.24.1"],
        check=True,
    )
    print("✅  onnxruntime>=1.24.1 (CPU) installed")


# ── .env file ─────────────────────────────────────────────────────────────────

def create_env_file() -> None:
    env_path = ROOT / ".env"
    example_path = ROOT / ".env.example"

    if env_path.exists():
        print(f"\nℹ️  .env already exists at {env_path} — skipping")
        return

    if not example_path.exists():
        print(f"\n⚠️  .env.example not found at {example_path}")
        return

    import shutil
    shutil.copy(example_path, env_path)
    print(f"\n✅  Created {env_path} from .env.example")
    print("   → Edit .env and set a strong SECRET_KEY before running in production!")


# ── Import verification ────────────────────────────────────────────────────────

def verify_imports() -> None:
    print("\n🔍  Verifying key imports...")
    checks = [
        ("fastapi", "FastAPI"),
        ("uvicorn", "uvicorn"),
        ("sqlalchemy", "SQLAlchemy"),
        ("passlib", "passlib"),
        ("jose", "python-jose"),
        ("torch", "PyTorch"),
        ("torchaudio", "torchaudio"),
        ("soundfile", "soundfile"),
        ("librosa", "librosa"),
        ("onnxruntime", "onnxruntime"),
        ("deepfilternet", "DeepFilterNet"),
    ]
    all_ok = True
    for module, label in checks:
        try:
            __import__(module)
            print(f"   ✅  {label}")
        except ImportError:
            print(f"   ❌  {label} — run: pip install -r requirements.txt")
            all_ok = False

    if all_ok:
        print("\n🎉  All imports verified successfully!")
    else:
        print("\n⚠️  Some imports failed. Run: pip install -r requirements.txt")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("  VoiceAuth — Environment Setup")
    print("=" * 60)

    # 1. GPU detection and onnxruntime setup
    cuda_available = check_cuda()
    if cuda_available:
        install_onnxruntime_gpu()
    else:
        install_onnxruntime_cpu()

    # 2. Create .env if missing
    create_env_file()

    # 3. Verify imports
    verify_imports()

    print("\n" + "=" * 60)
    print("  Setup complete!")
    print("  Next steps:")
    print("    python scripts/clone_repos.py")
    print("    python scripts/download_models.py")
    print("    python main.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
