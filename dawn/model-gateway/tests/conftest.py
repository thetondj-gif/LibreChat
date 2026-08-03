from __future__ import annotations

import sys
from pathlib import Path

# Keep test imports deterministic when pytest is launched through either the
# console entry point or `python -m pytest` in local and GitHub runners.
GATEWAY_ROOT = Path(__file__).resolve().parents[1]
if str(GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(GATEWAY_ROOT))
