"""Make `vad_scoring` importable when running `pytest tests/` from inside vad_scoring/."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
