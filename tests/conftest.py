import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_state_dir = Path(__file__).resolve().parent / "tmp_state"
_state_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("SCRIBE_STATE_PATH", str(_state_dir / "state.json"))
