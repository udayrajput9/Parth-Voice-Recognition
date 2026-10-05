#!/usr/bin/env python
"""
clone_repos.py — Clone required third-party GitHub repositories.

Repositories cloned into third_party/:
  - silero-vad    https://github.com/snakers4/silero-vad
  - aasist        https://github.com/clovaai/aasist
  - 3D-Speaker    https://github.com/alibaba-damo-academy/3D-Speaker

Note: DeepFilterNet is installed via pip (deepfilternet==0.5.6) and
      does NOT need to be cloned.

Usage:
    python scripts/clone_repos.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
THIRD_PARTY = ROOT / "third_party"

REPOS = [
    {
        "name": "silero-vad",
        "url": "https://github.com/snakers4/silero-vad.git",
        "dest": THIRD_PARTY / "silero-vad",
        "depth": 1,  # shallow clone — we only need the latest commit
    },
    {
        "name": "aasist",
        "url": "https://github.com/clovaai/aasist.git",
        "dest": THIRD_PARTY / "aasist",
        "depth": 1,
    },
    {
        "name": "3D-Speaker",
        "url": "https://github.com/alibaba-damo-academy/3D-Speaker.git",
        "dest": THIRD_PARTY / "3D-Speaker",
        "depth": 1,
    },
]


def check_git() -> bool:
    """Verify that git is installed and on PATH."""
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            print(f"✅  git found: {result.stdout.strip()}")
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    print("❌  git not found. Install git from https://git-scm.com/")
    return False


def clone_repo(repo: dict) -> bool:
    """Clone a single repository.  Returns True on success."""
    dest: Path = repo["dest"]
    name: str = repo["name"]
    url: str = repo["url"]

    # Already cloned?
    if (dest / ".git").exists():
        print(f"  ⏭️  {name} — already cloned at {dest}")
        return True

    # Create parent dir
    dest.parent.mkdir(parents=True, exist_ok=True)

    print(f"  🔄  Cloning {name} from {url} ...")
    cmd = ["git", "clone", "--depth", str(repo.get("depth", 1)), url, str(dest)]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            print(f"  ✅  {name} cloned to {dest}")
            return True
        else:
            print(f"  ❌  {name} clone failed:\n{result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  ❌  {name} clone timed out after 5 minutes")
        return False


def main() -> None:
    print("=" * 60)
    print("  VoiceAuth — Clone Third-Party Repositories")
    print("=" * 60)

    THIRD_PARTY.mkdir(parents=True, exist_ok=True)

    if not check_git():
        sys.exit(1)

    print()
    results = {}
    for repo in REPOS:
        results[repo["name"]] = clone_repo(repo)
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
        print("\n🎉  All repositories cloned successfully!")
        print("  Next: python scripts/download_models.py")
    else:
        print("\n⚠️  Some clones failed. Check your internet connection and try again.")
        sys.exit(1)


if __name__ == "__main__":
    main()
