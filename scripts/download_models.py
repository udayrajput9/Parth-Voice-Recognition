#!/usr/bin/env python
"""
download_models.py — Download AI model weight files.

Models downloaded:
  1. Silero VAD ONNX     → models/silero_vad/model.onnx
  2. AASIST checkpoint   → models/aasist/checkpoint/best_model.pth
  3. CAM++ checkpoint    → models/campp/checkpoint/campplus.bin

Usage:
    python scripts/download_models.py
    python scripts/download_models.py --skip-existing   (default behaviour)
    python scripts/download_models.py --force           (re-download all)
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent

MODELS = [
    {
        "name": "Silero VAD (ONNX)",
        "url": (
            "https://github.com/snakers4/silero-vad/raw/master/"
            "src/silero_vad/data/silero_vad.onnx"
        ),
        "dest": ROOT / "models" / "silero_vad" / "model.onnx",
        "size_hint": "~1.8 MB",
        "fallback": None,
    },
    {
        "name": "SSL+AASIST checkpoint (best_SSL_model_LA.pth)",
        "gdown_id": "1H2gEisq0lI0jC3x1F-iG4x4O2fI_vP7D",
        "url": "https://drive.google.com/uc?id=1H2gEisq0lI0jC3x1F-iG4x4O2fI_vP7D",
        "dest": ROOT / "models" / "ssl_aasist" / "checkpoint" / "best_SSL_model_LA.pth",
        "size_hint": "~1.2 GB",
        "fallback": (
            "⚠️  Google Drive download failed (quota exceeded?).\n"
            "   Download manually from:\n"
            "   https://drive.google.com/drive/folders/1c4ywztEVlYVijfwbGLl9OEa1SNtFKppB\n"
            "   and place the file at models/ssl_aasist/checkpoint/best_SSL_model_LA.pth"
        ),
    },
    {
        "name": "CAM++ speaker embedding (campplus.bin)",
        "url": (
            "https://modelscope.cn/api/v1/models/"
            "damo/speech_campplus_sv_zh-cn_16k-common/repo"
            "?Revision=master&FilePath=campplus_cn_common.bin"
        ),
        "dest": ROOT / "models" / "campp" / "checkpoint" / "campplus.bin",
        "size_hint": "~26 MB",
        "fallback": (
            "⚠️  ModelScope may require a browser download.\n"
            "   Alternatives:\n"
            "   1. Visit https://modelscope.cn/models/damo/speech_campplus_sv_zh-cn_16k-common\n"
            "      and download 'campplus_cn_common.bin'\n"
            "   2. OR use the 3D-Speaker download script:\n"
            "      cd third_party/3D-Speaker && python egs/3dspeaker/sv-cam++/run.sh\n"
            "   Place the file at: models/campp/checkpoint/campplus.bin"
        ),
    },
    {
        "name": "DeepFilterNet checkpoint (DeepFilterNet3.zip)",
        "url": "https://github.com/Rikorose/DeepFilterNet/raw/main/models/DeepFilterNet3.zip",
        "dest": ROOT / "models" / "deepfilternet" / "DeepFilterNet3.zip",
        "size_hint": "~8 MB",
        "fallback": "⚠️  Download manually from the URL and extract into models/deepfilternet/DeepFilterNet3",
        "unzip_to": ROOT / "models" / "deepfilternet",
    },
]


class ProgressBar:
    """Simple download progress reporter."""

    def __init__(self, filename: str):
        self.filename = filename
        self._last_pct = -1

    def __call__(self, count: int, block_size: int, total_size: int) -> None:
        if total_size <= 0:
            return
        pct = int(count * block_size * 100 / total_size)
        pct = min(pct, 100)
        if pct != self._last_pct and pct % 5 == 0:
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            print(f"\r  [{bar}] {pct:3d}%", end="", flush=True)
            self._last_pct = pct
        if pct == 100:
            print()  # newline after 100%


def download_file(url: str, dest: Path, name: str, unzip_to: Path | None = None, gdown_id: str | None = None) -> bool:
    """Download ``url`` to ``dest``. Returns True on success."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        if gdown_id:
            import gdown
            print(f"  🔄  Downloading from Google Drive via gdown ...")
            # gdown returns the path if successful, None if failed
            out = gdown.download(id=gdown_id, output=str(dest), quiet=False)
            if out is None:
                raise RuntimeError("gdown download failed (quota exceeded?)")
        else:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "VoiceAuth-ModelDownloader/1.0"},
            )
            progress = ProgressBar(dest.name)
            urllib.request.urlretrieve(url, dest, reporthook=progress)
            
        size_mb = dest.stat().st_size / (1024 * 1024)
        print(f"  ✅  Saved to {dest}  ({size_mb:.1f} MB)")
        
        if unzip_to:
            import zipfile
            print(f"  🔄  Extracting {dest.name} to {unzip_to} ...")
            with zipfile.ZipFile(dest, 'r') as zip_ref:
                zip_ref.extractall(unzip_to)
            print(f"  ✅  Extracted successfully.")
            
        return True
    except Exception as exc:
        print(f"\n  ❌  Download failed: {exc}")
        # Remove partial file
        if dest.exists():
            dest.unlink()
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Download VoiceAuth model weights")
    parser.add_argument("--force", action="store_true", help="Re-download even if file exists")
    args = parser.parse_args()

    print("=" * 60)
    print("  VoiceAuth — Download Model Weights")
    print("=" * 60)
    print()

    results: dict[str, bool] = {}

    for model in MODELS:
        name: str = model["name"]
        url: str = model["url"]
        dest: Path = model["dest"]
        size_hint: str = model["size_hint"]
        fallback: str | None = model.get("fallback")
        unzip_to: Path | None = model.get("unzip_to")
        gdown_id: str | None = model.get("gdown_id")

        print(f"📦  {name}  ({size_hint})")

        if dest.exists() and not args.force:
            size_mb = dest.stat().st_size / (1024 * 1024)
            print(f"  ⏭️  Already exists ({size_mb:.1f} MB) — skipping")
            print(f"     (use --force to re-download)\n")
            results[name] = True
            continue

        if gdown_id:
            print(f"  GDown ID: {gdown_id}")
        else:
            print(f"  URL: {url}")
            
        ok = download_file(url, dest, name, unzip_to, gdown_id)
        results[name] = ok

        if not ok and fallback:
            print(f"\n{fallback}\n")
        print()

    # Summary
    print("=" * 60)
    print("  Summary")
    print("=" * 60)
    all_ok = True
    for name, ok in results.items():
        status = "✅" if ok else "❌"
        print(f"  {status}  {name}")
        if not ok:
            all_ok = False

    if all_ok:
        print("\n🎉  All models downloaded!")
        print("  Ready to run: python main.py")
    else:
        print("\n⚠️  Some downloads failed. See fallback instructions above.")
        print("  Once weights are in place, run: python main.py")


if __name__ == "__main__":
    main()
