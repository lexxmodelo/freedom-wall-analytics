"""Make `import topic_modeling` resolvable from the tests directory regardless
of CWD. The package lives at <repo>/topic_modeling/topic_modeling/, so we add
the project root (parent of the package) to sys.path."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # .../topic_modeling/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
