"""Build the React UI so FastAPI can serve frontend/dist on Vercel."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FE = ROOT / "frontend"


def main() -> int:
    npm = "npm.cmd" if sys.platform.startswith("win") else "npm"
    subprocess.check_call([npm, "ci"], cwd=FE)
    subprocess.check_call([npm, "run", "build"], cwd=FE)
    dist = FE / "dist" / "index.html"
    if not dist.exists():
        raise SystemExit(f"frontend build missing {dist}")
    print(f"built {dist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
