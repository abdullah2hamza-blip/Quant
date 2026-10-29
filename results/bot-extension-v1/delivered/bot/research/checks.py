"""Run actual accounting, causality, restart, data and execution regression tests."""
from pathlib import Path
import subprocess
import sys
import uuid

def main():
    root = Path(__file__).resolve().parents[1]
    work = root / "state"
    work.mkdir(parents=True, exist_ok=True)
    return subprocess.run([sys.executable, "-m", "pytest", "tests", "-q", "--basetemp",
        str(work / ("pytest-" + uuid.uuid4().hex))], cwd=root).returncode


if __name__ == "__main__":
    raise SystemExit(main())
